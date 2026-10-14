"""Rádios, configuração da empresa e envios do aviso, no banco (por empresa, nunca em TOML).

- empresa_config: modelo da mensagem, nome que a mensagem fala, telefone de atendimento, limite de
  rejeição da planilha, fuso UTM e antecedência; sem linha, valem os padrões da distribuidora.
- radio: nome, e-mail, WhatsApp, o que alcança (municípios inteiros e comunidades com o distrito) e o
  valor padrão. Contato de empresa (a rádio), não de cliente.
- envio: cada envio de um município do aviso para uma rádio, com o valor e a forma de cobrança
  gravados no envio (mudar o preço da rádio depois não muda o passado), o custo, a economia, quem
  informou, o canal e a situação. O token de confirmação fica só como hash, vale 7 dias e uma vez.
- arquivo_envio: o PDF e o MP3 enviados, cifrados (AES-256-GCM, cofre.py) para baixar de novo.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from psycopg.rows import dict_row

from .conexao import conectar

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresa_config (
    empresa_id        bigint PRIMARY KEY REFERENCES empresa ON DELETE RESTRICT,
    modelo_mensagem   text,
    nome_mensagem     text,
    telefone          text,
    limite_rejeicao   numeric(5, 4) CHECK (limite_rejeicao BETWEEN 0 AND 1),
    epsg_utm          integer CHECK (epsg_utm BETWEEN 31960 AND 31985),
    antecedencia_dias integer CHECK (antecedencia_dias BETWEEN 1 AND 90),
    atualizado_por    bigint REFERENCES usuario ON DELETE RESTRICT,
    atualizado_em     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS radio (
    id            bigserial PRIMARY KEY,
    empresa_id    bigint NOT NULL REFERENCES empresa ON DELETE RESTRICT,
    nome          text NOT NULL,
    email         text,
    whatsapp      text,
    alcance       jsonb NOT NULL DEFAULT '{"municipios": [], "comunidades": []}',
    valor_padrao  numeric(12, 2),
    cobranca      text NOT NULL DEFAULT 'fechado' CHECK (cobranca IN ('fechado', 'minuto')),
    ativa         boolean NOT NULL DEFAULT true,
    criada_por    bigint REFERENCES usuario ON DELETE RESTRICT,
    criada_em     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS envio (
    id                bigserial PRIMARY KEY,
    empresa_id        bigint NOT NULL REFERENCES empresa ON DELETE RESTRICT,
    aviso_id          bigint NOT NULL REFERENCES aviso ON DELETE RESTRICT,
    municipio         text NOT NULL,
    municipio_nome    text NOT NULL,
    radio_id          bigint NOT NULL REFERENCES radio ON DELETE RESTRICT,
    radio_nome        text NOT NULL,
    canal             text NOT NULL CHECK (canal IN ('email', 'whatsapp', 'copia')),
    destino           text NOT NULL DEFAULT '',
    texto             text NOT NULL,
    valor             numeric(12, 2) NOT NULL,
    cobranca          text NOT NULL CHECK (cobranca IN ('fechado', 'minuto')),
    custo             numeric(12, 2) NOT NULL,
    custo_antigo      numeric(12, 2),
    economia          numeric(12, 2),
    economia_tipo     text CHECK (economia_tipo IN ('calculada', 'informada')),
    segundos          integer NOT NULL,
    segundos_hoje     integer,
    tempo_economizado integer,
    status            text NOT NULL CHECK (status IN ('preparando', 'enviado', 'entregue', 'falhou', 'confirmado')),
    criado_por        bigint REFERENCES usuario ON DELETE RESTRICT,
    criado_por_nome   text NOT NULL,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    token_hash        bytea UNIQUE,
    token_expira      timestamptz,
    confirmado_em     timestamptz
);
CREATE TABLE IF NOT EXISTS arquivo_envio (
    id         bigserial PRIMARY KEY,
    envio_id   bigint NOT NULL REFERENCES envio ON DELETE RESTRICT,
    empresa_id bigint NOT NULL REFERENCES empresa ON DELETE RESTRICT,
    tipo       text NOT NULL CHECK (tipo IN ('pdf', 'mp3')),
    nome       text NOT NULL,
    tamanho    integer NOT NULL,
    cifrado    bytea NOT NULL,
    UNIQUE (envio_id, tipo)
);
CREATE INDEX IF NOT EXISTS radio_empresa ON radio (empresa_id);
CREATE INDEX IF NOT EXISTS envio_aviso ON envio (aviso_id);
CREATE INDEX IF NOT EXISTS envio_empresa ON envio (empresa_id, criado_em DESC);
"""
VALIDADE_TOKEN = timedelta(days=7)


def criar_esquema(c) -> None:
    c.execute(ESQUEMA)


def _um(sql: str, args=()) -> dict | None:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchone() if cur.description else None


def _todos(sql: str, args=()) -> list[dict]:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


# ---------- Configuração da empresa ----------
def config(empresa_id: int) -> dict:
    return _um("SELECT * FROM empresa_config WHERE empresa_id = %s", (empresa_id,)) or {}


def salvar_config(empresa_id: int, usuario_id: int, dados: dict) -> None:
    campos = ("modelo_mensagem", "nome_mensagem", "telefone", "limite_rejeicao", "epsg_utm", "antecedencia_dias")
    _um("INSERT INTO empresa_config (empresa_id, atualizado_por, " + ", ".join(campos) + ") VALUES (%s, %s, "
        + ", ".join(["%s"] * len(campos)) + ") ON CONFLICT (empresa_id) DO UPDATE SET atualizado_por = EXCLUDED.atualizado_por,"
        " atualizado_em = now(), " + ", ".join(f"{c} = EXCLUDED.{c}" for c in campos),
        (empresa_id, usuario_id, *(dados.get(c) for c in campos)))


# ---------- Rádios ----------
RADIO = ("r.id, r.nome, r.email, r.whatsapp, r.alcance, r.valor_padrao, r.cobranca, r.ativa, r.criada_em,"
         " (SELECT e.valor FROM envio e WHERE e.radio_id = r.id ORDER BY e.id DESC LIMIT 1) AS ultimo_valor,"
         " (SELECT e.cobranca FROM envio e WHERE e.radio_id = r.id ORDER BY e.id DESC LIMIT 1) AS ultima_cobranca")


def radios(empresa_id: int, so_ativas: bool = True) -> list[dict]:
    return _todos(f"SELECT {RADIO} FROM radio r WHERE r.empresa_id = %s" + (" AND r.ativa" if so_ativas else "")
                  + " ORDER BY r.nome", (empresa_id,))


def radio(id_: int, empresa_id: int) -> dict | None:
    return _um(f"SELECT {RADIO} FROM radio r WHERE r.id = %s AND r.empresa_id = %s", (id_, empresa_id))


def criar_radio(empresa_id: int, usuario_id: int, d: dict) -> int:
    return _um("INSERT INTO radio (empresa_id, nome, email, whatsapp, alcance, valor_padrao, cobranca, criada_por)"
               " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (empresa_id, d["nome"], d["email"], d["whatsapp"], json.dumps(d["alcance"], ensure_ascii=False),
                d["valor_padrao"], d["cobranca"], usuario_id))["id"]


def alterar_radio(id_: int, empresa_id: int, d: dict) -> None:
    _um("UPDATE radio SET nome = %s, email = %s, whatsapp = %s, alcance = %s, valor_padrao = %s, cobranca = %s, ativa = %s"
        " WHERE id = %s AND empresa_id = %s",
        (d["nome"], d["email"], d["whatsapp"], json.dumps(d["alcance"], ensure_ascii=False), d["valor_padrao"],
         d["cobranca"], d["ativa"], id_, empresa_id))


# ---------- Envios ----------
ENVIO = ("e.id, e.aviso_id, e.municipio, e.municipio_nome, e.radio_id, e.radio_nome, e.canal, e.destino, e.texto, e.valor,"
         " e.cobranca, e.custo, e.custo_antigo, e.economia, e.economia_tipo, e.segundos, e.segundos_hoje, e.tempo_economizado,"
         " e.status, e.criado_por_nome, e.criado_em, e.confirmado_em,"
         " (SELECT array_agg(a.tipo ORDER BY a.tipo) FROM arquivo_envio a WHERE a.envio_id = e.id) AS arquivos")


def criar_envio(d: dict) -> int:
    campos = ("empresa_id", "aviso_id", "municipio", "municipio_nome", "radio_id", "radio_nome", "canal", "destino", "texto",
              "valor", "cobranca", "custo", "custo_antigo", "economia", "economia_tipo", "segundos", "segundos_hoje",
              "tempo_economizado", "status", "criado_por", "criado_por_nome")
    return _um(f"INSERT INTO envio ({', '.join(campos)}) VALUES ({', '.join('%(' + c + ')s' for c in campos)}) RETURNING id", d)["id"]


def definir_token(envio_id: int, token: str) -> datetime:
    expira = datetime.now(timezone.utc) + VALIDADE_TOKEN
    _um("UPDATE envio SET token_hash = %s, token_expira = %s WHERE id = %s", (hash_token(token), expira, envio_id))
    return expira


def mudar_status(envio_id: int, status: str) -> None:
    _um("UPDATE envio SET status = %s WHERE id = %s AND status <> 'confirmado'", (status, envio_id))


def envios(empresa_id: int, aviso_id: int | None = None) -> list[dict]:
    filtro = " AND e.aviso_id = %s" if aviso_id is not None else ""
    return _todos(f"SELECT {ENVIO} FROM envio e WHERE e.empresa_id = %s{filtro} ORDER BY e.id",
                  (empresa_id, aviso_id) if aviso_id is not None else (empresa_id,))


def envio(id_: int, empresa_id: int) -> dict | None:
    return _um(f"SELECT {ENVIO} FROM envio e WHERE e.id = %s AND e.empresa_id = %s", (id_, empresa_id))


def envio_pelo_token(token: str) -> dict | None:
    """O envio do token (só para mostrar a página de confirmação), com a validade e se já foi usado."""
    return _um("SELECT e.id, e.empresa_id, e.radio_nome, e.municipio_nome, e.status, e.token_expira, e.confirmado_em,"
               " a.data, a.horario FROM envio e JOIN aviso a ON a.id = e.aviso_id WHERE e.token_hash = %s", (hash_token(token),))


def confirmar(token: str) -> dict | None:
    """Usa o token uma vez, dentro da validade: o envio fica confirmado. None se não vale (vencido, usado, inexistente)."""
    return _um("UPDATE envio SET status = 'confirmado', confirmado_em = now() WHERE token_hash = %s AND confirmado_em IS NULL"
               " AND token_expira > now() RETURNING id, empresa_id, radio_nome, municipio_nome, aviso_id",
               (hash_token(token),))


# ---------- Arquivos cifrados ----------
def guardar_arquivo(envio_id: int, empresa_id: int, tipo: str, nome: str, tamanho: int, cifrado: bytes) -> None:
    _um("INSERT INTO arquivo_envio (envio_id, empresa_id, tipo, nome, tamanho, cifrado) VALUES (%s, %s, %s, %s, %s, %s)",
        (envio_id, empresa_id, tipo, nome, tamanho, cifrado))


def arquivo(envio_id: int, empresa_id: int, tipo: str) -> dict | None:
    return _um("SELECT nome, tamanho, cifrado FROM arquivo_envio WHERE envio_id = %s AND empresa_id = %s AND tipo = %s",
               (envio_id, empresa_id, tipo))
