"""Leitura do arquivo enviado (.csv ou .xlsx) como tabela de textos, em memória.

Nada é gravado em disco. O formato é decidido pelo conteúdo (um .xlsx é um zip), não pelo nome.
No .csv, o separador (; , ou tabulação) e a codificação (UTF-8 ou Latin-1, a do Excel no
Windows) são detectados.
"""

import csv
import io
import zipfile

import pandas as pd

from ..nucleo.planilha import PlanilhaInvalida

MAX_BYTES = 10 * 1024 * 1024
ZIP = b"PK\x03\x04"
# Zip bomb: o .xlsx é conferido pelo índice do zip antes do openpyxl abrir. O zipfile do Python não
# descompacta além do tamanho declarado no índice (passou disso, o arquivo é recusado como corrompido),
# então os tamanhos declarados limitam a memória de verdade.
MAX_DESCOMPACTADO = 100 * 1024 * 1024   # soma do conteúdo descompactado (50.000 linhas cabem com folga)
MAX_ENTRADAS = 500                      # arquivos dentro do .xlsx (um típico tem uns 10 a 30)
MAX_RAZAO = 200                         # descompactado / compactado de cada arquivo (XML de planilha: ~5 a 50)


def conferir_xlsx(conteudo: bytes) -> None:
    """Recusa o .xlsx que, descompactado, ficaria grande demais (zip bomb), antes de abri-lo."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            itens = z.infolist()
    except (zipfile.BadZipFile, ValueError, OSError):
        raise PlanilhaInvalida("Não foi possível ler o .xlsx (arquivo corrompido ou protegido por senha?).") from None
    if len(itens) > MAX_ENTRADAS:
        raise PlanilhaInvalida(f"O .xlsx tem arquivos internos demais (mais de {MAX_ENTRADAS}).")
    if sum(i.file_size for i in itens) > MAX_DESCOMPACTADO:
        raise PlanilhaInvalida("O .xlsx descompactado passa de 100 MB.")
    if any(i.file_size > MAX_RAZAO * max(i.compress_size, 1) for i in itens):
        raise PlanilhaInvalida("O .xlsx tem compactação fora do normal (possível arquivo malicioso).")


def ler(conteudo: bytes) -> pd.DataFrame:
    if not conteudo.strip():
        raise PlanilhaInvalida("O arquivo está vazio.")
    if len(conteudo) > MAX_BYTES:
        raise PlanilhaInvalida("O arquivo passa de 10 MB.")
    if conteudo.startswith(ZIP):
        conferir_xlsx(conteudo)
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
