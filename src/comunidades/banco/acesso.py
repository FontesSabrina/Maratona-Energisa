"""Acesso no banco: empresas, usuários, sessões, registro de atividades e histórico de avisos.

- Senha: só o hash Argon2id (quem calcula é api/acesso.py).
- Sessão: o banco guarda o SHA-256 do token, nunca o token; um vazamento da tabela não abre sessão.
- Registro: quem fez o quê e quando, sem dado de cliente (nada de UC, coordenada ou senha).
- Aviso: o resultado agregado de cada planilha (municípios, comunidades, contagens e o texto),
  nunca número de UC nem coordenada.
"""

import hashlib
import json
from datetime import datetime, timezone

from psycopg.rows import dict_row

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
    usuario_id  bigint REFERENCES usuario ON DELETE SET NULL,
    empresa_id  bigint REFERENCES empresa ON DELETE SET NULL,
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
CREATE INDEX IF NOT EXISTS sessao_usuario ON sessao (usuario_id);
CREATE INDEX IF NOT EXISTS registro_empresa ON registro (empresa_id, quando DESC);
CREATE INDEX IF NOT EXISTS aviso_empresa ON aviso (empresa_id, criado_em DESC);
"""


def criar_esquema() -> None:
    with conectar() as c:
        if esquema():
            c.execute(f'CREATE SCHEMA IF NOT EXISTS "{esquema()}"')
        c.execute(ESQUEMA)


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
           " u.ultimo_acesso, u.criado_em, e.nome AS empresa_nome, e.sigla AS empresa_sigla, e.status AS empresa_status")


# ---------- Empresas ----------
def empresa_por_sigla(sigla: str) -> dict | None:
    return _um("SELECT * FROM empresa WHERE sigla = %s", (sigla,))


def criar_empresa(nome: str, sigla: str, dominio: str) -> dict:
    return _executar("INSERT INTO empresa (nome, sigla, dominio) VALUES (%s, %s, %s) RETURNING *", (nome, sigla, dominio))


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


def criar_usuario(empresa_id: int | None, email: str, nome: str, perfil: str, senha_hash: str, trocar_senha: bool = True) -> dict:
    return _executar("INSERT INTO usuario (empresa_id, email, nome, perfil, senha_hash, trocar_senha)"
                     " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", (empresa_id, email, nome, perfil, senha_hash, trocar_senha))


def alterar_usuario(id_: int, perfil: str, status: str) -> None:
    _executar("UPDATE usuario SET perfil = %s, status = %s WHERE id = %s", (perfil, status, id_))
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
def registrar(acao: str, detalhe: str = "", usuario_id: int | None = None, empresa_id: int | None = None) -> None:
    _executar("INSERT INTO registro (usuario_id, empresa_id, acao, detalhe) VALUES (%s, %s, %s, %s)",
              (usuario_id, empresa_id, acao, detalhe[:500]))


def registros(empresa_id: int | None, limite: int = 200) -> list[dict]:
    """Registro da empresa (ou de tudo, com empresa_id None), do mais recente para o mais antigo."""
    filtro = "WHERE r.empresa_id = %s" if empresa_id is not None else ""
    args = (empresa_id, limite) if empresa_id is not None else (limite,)
    return _todos("SELECT r.id, r.quando, r.acao, r.detalhe, u.nome AS usuario, u.email, e.sigla AS empresa"
                  " FROM registro r LEFT JOIN usuario u ON u.id = r.usuario_id LEFT JOIN empresa e ON e.id = r.empresa_id"
                  f" {filtro} ORDER BY r.quando DESC, r.id DESC LIMIT %s", args)


# ---------- Histórico de avisos (só o agregado) ----------
def gravar_aviso(empresa_id: int, usuario_id: int, data: str, horario: str, idioma: str, resumo: dict, municipios: list) -> int:
    return _executar("INSERT INTO aviso (empresa_id, usuario_id, data, horario, idioma, resumo, municipios)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                     (empresa_id, usuario_id, data, horario, idioma, json.dumps(resumo, ensure_ascii=False),
                      json.dumps(municipios, ensure_ascii=False)))["id"]


def avisos(empresa_id: int, limite: int = 100) -> list[dict]:
    return _todos("SELECT a.id, a.criado_em, a.data, a.horario, a.idioma, a.resumo, a.municipios, u.nome AS usuario"
                  " FROM aviso a LEFT JOIN usuario u ON u.id = a.usuario_id WHERE a.empresa_id = %s"
                  " ORDER BY a.criado_em DESC, a.id DESC LIMIT %s", (empresa_id, limite))


def aviso(id_: int, empresa_id: int) -> dict | None:
    return _um("SELECT a.*, u.nome AS usuario FROM aviso a LEFT JOIN usuario u ON u.id = a.usuario_id"
               " WHERE a.id = %s AND a.empresa_id = %s", (id_, empresa_id))


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
