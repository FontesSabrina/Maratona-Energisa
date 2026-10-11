"""Conexão com o Postgres (banco fazendadb, com PostGIS).

O endereço vem da variável de ambiente DATABASE_URL ou, se ela não estiver definida, do arquivo
.env na raiz do projeto (ignorado pelo git). Nenhuma senha fica no código.
"""

import os

import psycopg

from .. import config as C

ARQ_ENV = C.RAIZ / ".env"


def url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if ARQ_ENV.exists():
        for linha in ARQ_ENV.read_text(encoding="utf-8").splitlines():
            nome, _, valor = linha.strip().partition("=")
            if nome.strip() == "DATABASE_URL" and valor.strip():
                return valor.strip().strip('"').strip("'")
    raise RuntimeError("DATABASE_URL não definida (variável de ambiente ou .env na raiz do projeto)")


def conectar() -> psycopg.Connection:
    return psycopg.connect(url())
