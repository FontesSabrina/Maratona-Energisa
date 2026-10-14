"""Acesso no banco: empresas, usuários, sessões, registro de atividades e histórico de avisos.

- Senha: só o hash Argon2id (quem calcula é api/acesso.py).
- Sessão: o banco guarda o SHA-256 do token, nunca o token; um vazamento da tabela não abre sessão.
- Registro (auditoria): quem fez o quê e quando, sem dado de cliente (nada de UC, coordenada ou senha).
  Só inclusão (gatilhos recusam UPDATE, DELETE e TRUNCATE) e encadeado por hash (nucleo/auditoria.py):
  cada linha guarda o nome e o perfil de quem fez, copiados do login, e o hash da linha anterior.
- Aviso: o resultado agregado de cada planilha (municípios, comunidades, contagens e o texto),
  nunca número de UC nem coordenada.
"""

import hashlib
import json
from datetime import datetime, timezone

from psycopg.rows import dict_row

from ..nucleo import auditoria
from . import radios
from .conexao import conectar, esquema

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresa (
    id          bigserial PRIMARY KEY,
    nome        text NOT NULL,
    sigla       text NOT NULL UNIQUE,
    dominio     text NOT NULL,
    status      text NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'suspensa')),
    criada_em   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS usuario (
    id             bigserial PRIMARY KEY,
    empresa_id     bigint REFERENCES empresa ON DELETE RESTRICT,
    email          text NOT NULL UNIQUE CHECK (email = lower(email)),
    nome           text NOT NULL,
    perfil         text NOT NULL CHECK (perfil IN ('admin_farol', 'admin_empresa', 'operador', 'consulta')),
    senha_hash     text NOT NULL,
    trocar_senha   boolean NOT NULL DEFAULT true,
    status         text NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'bloqueado')),
    tentativas     integer NOT NULL DEFAULT 0,
    bloqueado_ate  timestamptz,
    criado_em      timestamptz NOT NULL DEFAULT now(),
    ultimo_acesso  timestamptz,
    CHECK ((perfil = 'admin_farol') = (empresa_id IS NULL))
);
CREATE TABLE IF NOT EXISTS sessao (
    token_hash  bytea PRIMARY KEY,
    usuario_id  bigint NOT NULL REFERENCES usuario ON DELETE CASCADE,
    criada_em   timestamptz NOT NULL DEFAULT now(),
    ultimo_uso  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS registro (
    id          bigserial PRIMARY KEY,
    quando      timestamptz NOT NULL DEFAULT now(),
    usuario_id  bigint REFERENCES usuario ON DELETE RESTRICT,
    empresa_id  bigint REFERENCES empresa ON DELETE RESTRICT,
    acao        text NOT NULL,
    detalhe     text NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS aviso (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL REFERENCES empresa ON DELETE RESTRICT,
    usuario_id  bigint REFERENCES usuario ON DELETE SET NULL,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    data        text NOT NULL,
    horario     text NOT NULL,
    idioma      text NOT NULL,
    resumo      jsonb NOT NULL,    -- linhas, válidas, problemas, fora da concessão, prazo
    municipios  jsonb NOT NULL     -- por município: comunidades, contagens, aviso gerado e texto final
);
-- municípios em que o usuário atua e o CNPJ da empresa (opcional), desde 14/10/2026
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS municipios jsonb NOT NULL DEFAULT '[]';
ALTER TABLE empresa ADD COLUMN IF NOT EXISTS cnpj text;
-- auditoria encadeada (desde 14/10/2026): quem fez (cópia do login), perfil e os hashes
ALTER TABLE registro ADD COLUMN IF NOT EXISTS usuario_nome text, ADD COLUMN IF NOT EXISTS perfil text,
    ADD COLUMN IF NOT EXISTS hash_anterior text, ADD COLUMN IF NOT EXISTS hash text;
-- o aviso: tipo e motivo do desligamento, situação, código de verificação e quem pediu (cópia do login)
ALTER TABLE aviso ADD COLUMN IF NOT EXISTS tipo text, ADD COLUMN IF NOT EXISTS motivo text,
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'gerado', ADD COLUMN IF NOT EXISTS codigo text,
    ADD COLUMN IF NOT EXISTS solicitante text, ADD COLUMN IF NOT EXISTS solicitante_perfil text;
-- quem tem linha no registro não pode ser apagado (apagar mudaria a auditoria)
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'registro'::regclass AND contype = 'f' AND confdeltype = 'n') THEN
    ALTER TABLE registro DROP CONSTRAINT IF EXISTS registro_usuario_id_fkey, DROP CONSTRAINT IF EXISTS registro_empresa_id_fkey,
      ADD CONSTRAINT registro_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES usuario ON DELETE RESTRICT,
      ADD CONSTRAINT registro_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES empresa ON DELETE RESTRICT;
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS registro_hash ON registro (hash);
CREATE INDEX IF NOT EXISTS aviso_codigo ON aviso (codigo);
CREATE INDEX IF NOT EXISTS sessao_usuario ON sessao (usuario_id);
CREATE INDEX IF NOT EXISTS registro_empresa ON registro (empresa_id, quando DESC);
CREATE INDEX IF NOT EXISTS aviso_empresa ON aviso (empresa_id, criado_em DESC);
"""


# o registro é só inclusão: alterar, apagar ou truncar dá erro no próprio banco
SO_INCLUSAO = """
CREATE OR REPLACE FUNCTION registro_so_inclusao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'registro de auditoria: só inclusão (nada é alterado nem apagado; correção é uma linha nova)';
END $$;
DROP TRIGGER IF EXISTS registro_sem_alterar ON registro;
CREATE TRIGGER registro_sem_alterar BEFORE UPDATE OR DELETE ON registro FOR EACH ROW EXECUTE FUNCTION registro_so_inclusao();
DROP TRIGGER IF EXISTS registro_sem_truncar ON registro;
CREATE TRIGGER registro_sem_truncar BEFORE TRUNCATE ON registro FOR EACH STATEMENT EXECUTE FUNCTION registro_so_inclusao();
"""
TRAVA_REGISTRO = 7_020_126   # pg_advisory_xact_lock: uma linha da corrente por vez


def criar_esquema() -> None:
    with conectar() as c:
        if esquema():
            c.execute(f'CREATE SCHEMA IF NOT EXISTS "{esquema()}"')
        c.execute(ESQUEMA)
        _encadear_antigas(c)
        c.execute(SO_INCLUSAO)
        radios.criar_esquema(c)   # rádios, configuração da empresa e envios (dependem de empresa, usuário e aviso)


def _encadear_antigas(c) -> None:
    """Uma vez só, na migração: as linhas de antes da auditoria encadeada ganham nome, perfil e hashes."""
    if not c.execute("SELECT 1 FROM registro WHERE hash IS NULL LIMIT 1").fetchone():
        return
    c.execute("ALTER TABLE registro DISABLE TRIGGER USER")
    with c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT r.*, u.nome AS nome_atual, u.perfil AS perfil_atual FROM registro r"
                    " LEFT JOIN usuario u ON u.id = r.usuario_id ORDER BY r.id")
        anterior = auditoria.INICIO
        for ln in cur.fetchall():
            ln = {**ln, "usuario_nome": ln["usuario_nome"] or ln["nome_atual"], "perfil": ln["perfil"] or ln["perfil_atual"],
                  "hash_anterior": anterior}
            ln["hash"] = auditoria.hash_linha(ln)
            c.execute("UPDATE registro SET usuario_nome = %s, perfil = %s, hash_anterior = %s, hash = %s WHERE id = %s",
                      (ln["usuario_nome"], ln["perfil"], ln["hash_anterior"], ln["hash"], ln["id"]))
            anterior = ln["hash"]
    c.execute("ALTER TABLE registro ENABLE TRIGGER USER")


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _um(sql: str, args=()) -> dict | None:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def _todos(sql: str, args=()) -> list[dict]:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def _executar(sql: str, args=()) -> dict | None:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchone() if cur.description else None


USUARIO = ("u.id, u.empresa_id, u.email, u.nome, u.perfil, u.trocar_senha, u.status, u.tentativas, u.bloqueado_ate,"
           " u.ultimo_acesso, u.criado_em, u.municipios, e.nome AS empresa_nome, e.sigla AS empresa_sigla, e.status AS empresa_status")


# ---------- Empresas ----------
def empresa_por_sigla(sigla: str) -> dict | None:
    return _um("SELECT * FROM empresa WHERE sigla = %s", (sigla,))


def criar_empresa(nome: str, sigla: str, dominio: str, cnpj: str | None = None) -> dict:
    return _executar("INSERT INTO empresa (nome, sigla, dominio, cnpj) VALUES (%s, %s, %s, %s) RETURNING *", (nome, sigla, dominio, cnpj))


def empresa_por_cnpj(cnpj: str) -> dict | None:
    return _um("SELECT * FROM empresa WHERE cnpj = %s", (cnpj,))


def mudar_status_empresa(id_: int, status: str) -> None:
    """Suspende ou reativa; suspensa, as sessões dos usuários dela acabam (e o login é recusado)."""
    _executar("UPDATE empresa SET status = %s WHERE id = %s", (status, id_))
    if status == "suspensa":
        _executar("DELETE FROM sessao WHERE usuario_id IN (SELECT id FROM usuario WHERE empresa_id = %s)", (id_,))


def empresa(id_: int) -> dict | None:
    return _um("SELECT * FROM empresa WHERE id = %s", (id_,))


def empresas() -> list[dict]:
    return _todos("SELECT e.*, (SELECT count(*) FROM usuario u WHERE u.empresa_id = e.id) AS usuarios,"
                  " (SELECT count(*) FROM aviso a WHERE a.empresa_id = e.id) AS avisos FROM empresa e ORDER BY e.nome")


# ---------- Usuários ----------
def usuario_por_email(email: str) -> dict | None:
    return _um(f"SELECT {USUARIO}, u.senha_hash FROM usuario u LEFT JOIN empresa e ON e.id = u.empresa_id WHERE u.email = %s", (email,))


def usuario(id_: int) -> dict | None:
    return _um(f"SELECT {USUARIO}, u.senha_hash FROM usuario u LEFT JOIN empresa e ON e.id = u.empresa_id WHERE u.id = %s", (id_,))


def usuarios(empresa_id: int) -> list[dict]:
    return _todos(f"SELECT {USUARIO} FROM usuario u LEFT JOIN empresa e ON e.id = u.empresa_id"
                  " WHERE u.empresa_id = %s ORDER BY u.nome", (empresa_id,))


def admins_ativos(empresa_id: int) -> int:
    return _um("SELECT count(*) AS n FROM usuario WHERE empresa_id = %s AND perfil = 'admin_empresa' AND status = 'ativo'",
               (empresa_id,))["n"]


def criar_usuario(empresa_id: int | None, email: str, nome: str, perfil: str, senha_hash: str, trocar_senha: bool = True,
                  municipios: list[str] | None = None) -> dict:
    return _executar("INSERT INTO usuario (empresa_id, email, nome, perfil, senha_hash, trocar_senha, municipios)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                     (empresa_id, email, nome, perfil, senha_hash, trocar_senha, json.dumps(municipios or [])))


def alterar_usuario(id_: int, perfil: str, status: str, municipios: list[str] | None = None) -> None:
    _executar("UPDATE usuario SET perfil = %s, status = %s, municipios = COALESCE(%s, municipios) WHERE id = %s",
              (perfil, status, json.dumps(municipios) if municipios is not None else None, id_))
    if status == "bloqueado":
        encerrar_sessoes(id_)


def definir_senha(id_: int, senha_hash: str, trocar_senha: bool) -> None:
    _executar("UPDATE usuario SET senha_hash = %s, trocar_senha = %s, tentativas = 0, bloqueado_ate = NULL WHERE id = %s",
              (senha_hash, trocar_senha, id_))


def registrar_falha(id_: int, max_tentativas: int, bloqueio) -> dict:
    """Mais uma senha errada; na última permitida, bloqueia por um tempo e zera a contagem."""
    return _executar("UPDATE usuario SET tentativas = CASE WHEN tentativas + 1 >= %s THEN 0 ELSE tentativas + 1 END,"
                     " bloqueado_ate = CASE WHEN tentativas + 1 >= %s THEN now() + %s ELSE bloqueado_ate END"
                     " WHERE id = %s RETURNING tentativas, bloqueado_ate", (max_tentativas, max_tentativas, bloqueio, id_))


def registrar_acesso(id_: int, senha_hash: str | None = None) -> None:
    _executar("UPDATE usuario SET tentativas = 0, bloqueado_ate = NULL, ultimo_acesso = now(),"
              " senha_hash = COALESCE(%s, senha_hash) WHERE id = %s", (senha_hash, id_))


# ---------- Sessões ----------
def criar_sessao(usuario_id: int, token: str) -> None:
    _executar("INSERT INTO sessao (token_hash, usuario_id) VALUES (%s, %s)", (hash_token(token), usuario_id))


def sessao(token: str, inativa, maxima) -> dict | None:
    """O usuário da sessão, se ela ainda vale (e marca o uso); a sessão vencida é apagada."""
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("DELETE FROM sessao WHERE token_hash = %s AND (ultimo_uso < now() - %s OR criada_em < now() - %s)",
                    (hash_token(token), inativa, maxima))
        cur.execute(f"UPDATE sessao s SET ultimo_uso = now() FROM usuario u LEFT JOIN empresa e ON e.id = u.empresa_id"
                    f" WHERE s.token_hash = %s AND u.id = s.usuario_id RETURNING {USUARIO}", (hash_token(token),))
        return cur.fetchone()


def encerrar_sessao(token: str) -> None:
    _executar("DELETE FROM sessao WHERE token_hash = %s", (hash_token(token),))


def encerrar_sessoes(usuario_id: int, exceto_token: str | None = None) -> None:
    _executar("DELETE FROM sessao WHERE usuario_id = %s AND token_hash IS DISTINCT FROM %s",
              (usuario_id, hash_token(exceto_token) if exceto_token else None))


# ---------- Registro de atividades ----------
def _registrar(c, acao: str, detalhe: str, usuario_id: int | None, empresa_id: int | None) -> dict:
    """Uma linha nova na corrente, dentro da transação de quem chama (com a trava, uma por vez)."""
    c.execute("SELECT pg_advisory_xact_lock(%s)", (TRAVA_REGISTRO,))
    quem = c.execute("SELECT nome, perfil FROM usuario WHERE id = %s", (usuario_id,)).fetchone() if usuario_id else None
    ultimo = c.execute("SELECT hash FROM registro ORDER BY id DESC LIMIT 1").fetchone()
    linha = {"id": c.execute("SELECT nextval(pg_get_serial_sequence('registro', 'id'))").fetchone()[0],
             "quando": datetime.now(timezone.utc), "empresa_id": empresa_id, "usuario_id": usuario_id,
             "usuario_nome": quem[0] if quem else None, "perfil": quem[1] if quem else None,
             "acao": acao, "detalhe": str(detalhe)[:500], "hash_anterior": ultimo[0] if ultimo else auditoria.INICIO}
    linha["hash"] = auditoria.hash_linha(linha)
    c.execute("INSERT INTO registro (id, quando, usuario_id, empresa_id, usuario_nome, perfil, acao, detalhe, hash_anterior, hash)"
              " VALUES (%(id)s, %(quando)s, %(usuario_id)s, %(empresa_id)s, %(usuario_nome)s, %(perfil)s, %(acao)s, %(detalhe)s,"
              " %(hash_anterior)s, %(hash)s)", linha)
    return linha


def registrar(acao: str, detalhe: str = "", usuario_id: int | None = None, empresa_id: int | None = None) -> dict:
    """Registra uma ação na auditoria (só inclusão, encadeada) e devolve a linha com o hash."""
    with conectar() as c:
        return _registrar(c, acao, detalhe, usuario_id, empresa_id)


def registros(empresa_id: int | None, limite: int = 200) -> list[dict]:
    """Registro da empresa (ou de tudo, com empresa_id None), do mais recente para o mais antigo.
    O nome e o perfil são os de quando a ação foi feita (copiados na linha)."""
    filtro = "WHERE r.empresa_id = %s" if empresa_id is not None else ""
    args = (empresa_id, limite) if empresa_id is not None else (limite,)
    return _todos("SELECT r.id, r.quando, r.acao, r.detalhe, r.usuario_nome AS usuario, r.perfil, r.hash, e.sigla AS empresa"
                  " FROM registro r LEFT JOIN empresa e ON e.id = r.empresa_id"
                  f" {filtro} ORDER BY r.id DESC LIMIT %s", args)


def verificar_registro() -> dict:
    """Confere a corrente inteira do registro (nucleo/auditoria.verificar)."""
    return auditoria.verificar(_todos("SELECT id, quando, empresa_id, usuario_id, usuario_nome, perfil, acao, detalhe, hash_anterior, hash"
                                      " FROM registro ORDER BY id"))


def linha_por_hash(prefixo: str) -> dict | None:
    """A linha do registro cujo hash começa com o prefixo (o código de verificação, sem o FRL- e os traços)."""
    return _um("SELECT r.id, r.quando, r.acao, r.detalhe, r.usuario_nome AS usuario, r.perfil, r.hash, r.empresa_id"
               " FROM registro r WHERE r.hash LIKE %s ORDER BY r.id LIMIT 1", (prefixo.lower() + "%",))


# ---------- Histórico de avisos (só o agregado) ----------
def gravar_aviso(empresa_id: int, usuario_id: int, data: str, horario: str, idioma: str, resumo: dict, municipios: list,
                 tipo: str, motivo: str, detalhe_registro) -> dict:
    """Grava o aviso e a linha "gerou aviso" na auditoria na mesma transação; o código de verificação do
    aviso sai do hash dessa linha. detalhe_registro(id) monta o detalhe com o número do aviso."""
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT nome, perfil FROM usuario WHERE id = %s", (usuario_id,))
        quem = cur.fetchone()
        cur.execute("INSERT INTO aviso (empresa_id, usuario_id, data, horario, idioma, resumo, municipios, tipo, motivo, solicitante,"
                    " solicitante_perfil) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, criado_em",
                    (empresa_id, usuario_id, data, horario, idioma, json.dumps(resumo, ensure_ascii=False),
                     json.dumps(municipios, ensure_ascii=False), tipo, motivo, quem["nome"], quem["perfil"]))
        a = cur.fetchone()
        linha = _registrar(c, "gerou aviso", detalhe_registro(a["id"]), usuario_id, empresa_id)
        codigo = auditoria.codigo_verificacao(linha["hash"])
        cur.execute("UPDATE aviso SET codigo = %s WHERE id = %s", (codigo, a["id"]))
        return {"id": a["id"], "criado_em": a["criado_em"], "codigo": codigo, "solicitante": quem["nome"],
                "solicitante_perfil": quem["perfil"]}


AVISO = ("a.id, a.criado_em, a.data, a.horario, a.idioma, a.resumo, a.municipios, a.tipo, a.motivo, a.status, a.codigo,"
         " COALESCE(a.solicitante, u.nome) AS usuario, COALESCE(a.solicitante_perfil, u.perfil) AS usuario_perfil")


def avisos(empresa_id: int, limite: int = 100) -> list[dict]:
    return _todos(f"SELECT {AVISO} FROM aviso a LEFT JOIN usuario u ON u.id = a.usuario_id WHERE a.empresa_id = %s"
                  " ORDER BY a.criado_em DESC, a.id DESC LIMIT %s", (empresa_id, limite))


def aviso(id_: int, empresa_id: int) -> dict | None:
    return _um(f"SELECT {AVISO} FROM aviso a LEFT JOIN usuario u ON u.id = a.usuario_id"
               " WHERE a.id = %s AND a.empresa_id = %s", (id_, empresa_id))


def atualizar_municipios(id_: int, empresa_id: int, municipios: list) -> None:
    """Os municípios do aviso com a mensagem final (que só tem o código depois de gravado o aviso)."""
    _executar("UPDATE aviso SET municipios = %s WHERE id = %s AND empresa_id = %s",
              (json.dumps(municipios, ensure_ascii=False), id_, empresa_id))


def cancelar_aviso(id_: int, empresa_id: int) -> bool:
    return _executar("UPDATE aviso SET status = 'cancelado' WHERE id = %s AND empresa_id = %s AND status <> 'cancelado' RETURNING id",
                     (id_, empresa_id)) is not None


def mudar_data(id_: int, empresa_id: int, data: str, horario: str) -> bool:
    return _executar("UPDATE aviso SET data = %s, horario = %s WHERE id = %s AND empresa_id = %s AND status <> 'cancelado' RETURNING id",
                     (data, horario, id_, empresa_id)) is not None


def texto_final(id_: int, empresa_id: int, codigo: str, texto: str) -> bool:
    """Grava o texto que foi para a rádio (depois da edição) no município do aviso."""
    a = aviso(id_, empresa_id)
    if not a:
        return False
    ms = a["municipios"]
    alvo = next((m for m in ms if m["codigo_ibge"] == codigo), None)
    if not alvo:
        return False
    alvo["texto_final"], alvo["texto_final_em"] = texto, datetime.now(timezone.utc).isoformat(timespec="seconds")
    _executar("UPDATE aviso SET municipios = %s WHERE id = %s AND empresa_id = %s",
              (json.dumps(ms, ensure_ascii=False), id_, empresa_id))
    return True
