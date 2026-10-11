"""Conexão com o Postgres (banco fazendadb, com PostGIS).

O endereço vem da variável de ambiente DATABASE_URL ou, se ela não estiver definida, do arquivo
.env na raiz do projeto (ignorado pelo git). Nenhuma senha fica no código.
"""

import os

import psycopg

from .. import config as C

# FAROL_ENV escolhe outro arquivo (ex.: .env.producao, para a semente no banco de produção)
ARQ_ENV = C.RAIZ / (os.environ.get("FAROL_ENV") or ".env")


def url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if ARQ_ENV.exists():
        for linha in ARQ_ENV.read_text(encoding="utf-8").splitlines():
            nome, _, valor = linha.strip().partition("=")
            if nome.strip() == "DATABASE_URL" and valor.strip():
                return valor.strip().strip('"').strip("'")
    raise RuntimeError("DATABASE_URL não definida (variável de ambiente ou .env na raiz do projeto)")


def esquema() -> str | None:
    """FAROL_ESQUEMA: esquema do Postgres para as tabelas de acesso (os testes usam um próprio e apagam
    no fim). O public continua no caminho, para o PostGIS e a base territorial."""
    e = os.environ.get("FAROL_ESQUEMA", "").strip()
    if e and not (e.isidentifier() and e.isascii() and e.islower()):
        raise RuntimeError("FAROL_ESQUEMA: use só letras minúsculas, números e _")
    return e or None


def conectar() -> psycopg.Connection:
    e = esquema()
    return psycopg.connect(url(), options=f"-c search_path={e},public" if e else None)
