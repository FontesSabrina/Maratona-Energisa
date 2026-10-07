"""Download dos dados brutos do IBGE (feito uma vez; depois reaproveita o que já está em data/raw)."""

import shutil
import urllib.request
import zipfile
from pathlib import Path

from .. import config as C

ARQUIVOS = {
    "3138401_LEOPOLDINA.zip": (
        "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
        "Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/31_MG/3138401_LEOPOLDINA.zip"
    ),
    "Localidades_UFs_gpkg.zip": (
        "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/"
        "Localidades_do_Brasil/2022/Localidades_UFs_gpkg.zip"
    ),
    "MG_setores_CD2022.zip": (
        "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
        "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/setores/shp/UF/MG_setores_CD2022.zip"
    ),
}


def _baixar(url: str, destino: Path):
    print(f"  baixando {destino.name} (pode levar alguns minutos)...", flush=True)
    tmp = destino.with_suffix(".parcial")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.replace(destino)


def garantir():
    C.RAW.mkdir(parents=True, exist_ok=True)
    for nome, url in ARQUIVOS.items():
        if not (C.RAW / nome).exists():
            _baixar(url, C.RAW / nome)
    if not C.ARQ_CNEFE.exists():
        zipfile.ZipFile(C.RAW / "3138401_LEOPOLDINA.zip").extractall(C.RAW / "cnefe")
    if not C.ARQ_LOCALIDADES.exists():
        with zipfile.ZipFile(C.RAW / "Localidades_UFs_gpkg.zip") as z:
            z.extractall(C.RAW / "localidades", members=[m for m in z.namelist() if m.startswith("MG/")])
    if not C.ARQ_SETORES.exists():
        zipfile.ZipFile(C.RAW / "MG_setores_CD2022.zip").extractall(C.RAW / "setores_mg")


if __name__ == "__main__":
    garantir()
