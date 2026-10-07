"""Caminhos e parâmetros globais do projeto."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DADOS = RAIZ / "data"
RAW = DADOS / "raw"
INTERIM = DADOS / "interim"   # dados reais recortados/limpos (IBGE, OSM)
SINTETICO = DADOS / "sintetico"  # camadas fictícias da distribuidora
SAIDA = RAIZ / "saida"

COD_MUNICIPIO = "3138401"  # Leopoldina - MG
NOME_MUNICIPIO = "Leopoldina"

CRS_GEO = "EPSG:4674"      # SIRGAS 2000 (lat/long), padrão IBGE
CRS_METRICO = "EPSG:31983"  # SIRGAS 2000 / UTM 23S, para distâncias em metros
CRS_WEB = "EPSG:4326"

SEMENTE = 42  # reprodutibilidade de tudo que é sorteado

ARQ_CNEFE = RAW / "cnefe" / "3138401_LEOPOLDINA.csv"
ARQ_LOCALIDADES = RAW / "localidades" / "MG" / "MG_localidades_2022.gpkg"
ARQ_SETORES = RAW / "setores_mg" / "MG_setores_CD2022.shp"

for _p in (INTERIM, SINTETICO, SAIDA):
    _p.mkdir(parents=True, exist_ok=True)
