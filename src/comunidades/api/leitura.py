"""Leitura do arquivo enviado (.csv ou .xlsx) como tabela de textos, em memória.

Nada é gravado em disco. O formato é decidido pelo conteúdo (um .xlsx é um zip), não pelo nome.
No .csv, o separador (; , ou tabulação) e a codificação (UTF-8 ou Latin-1, a do Excel no
Windows) são detectados.
"""

import csv
import io

import pandas as pd

from ..nucleo.planilha import PlanilhaInvalida

MAX_BYTES = 10 * 1024 * 1024
ZIP = b"PK\x03\x04"


def ler(conteudo: bytes) -> pd.DataFrame:
    if not conteudo.strip():
        raise PlanilhaInvalida("O arquivo está vazio.")
    if len(conteudo) > MAX_BYTES:
        raise PlanilhaInvalida("O arquivo passa de 10 MB.")
    if conteudo.startswith(ZIP):
        try:
            t = pd.read_excel(io.BytesIO(conteudo), dtype=str, engine="openpyxl", sheet_name=0)
        except Exception:
            raise PlanilhaInvalida("Não foi possível ler o .xlsx (arquivo corrompido ou protegido por senha?).") from None
    else:
        try:
            texto = conteudo.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = conteudo.decode("latin-1")
        amostra = texto[:20_000]
        try:
            sep = csv.Sniffer().sniff(amostra, delimiters=";,\t").delimiter
        except csv.Error:
            sep = ";" if amostra.count(";") >= amostra.count(",") else ","
        try:
            t = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
        except Exception:
            raise PlanilhaInvalida("Não foi possível ler o .csv (formato inesperado).") from None
    t.columns = [str(c).strip() for c in t.columns]
    return t.dropna(how="all")
