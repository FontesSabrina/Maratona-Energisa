"""Camadas REAIS do IBGE (Censo 2022) do município configurado e construção do gabarito.

Gabarito = comunidade de cada endereço, a partir do campo DSC_LOCALIDADE do CNEFE,
limpo: rótulos genéricos ("ESTRADA", "FAZENDA"...), nomes de propriedade
("SITIO X", "FAZENDA Y") e grupos muito pequenos são reatribuídos à comunidade
predominante entre os vizinhos mais próximos.
"""

import re

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.neighbors import KNeighborsClassifier
from unidecode import unidecode

from .. import config as C

# Rótulos que não são nome de comunidade ("ESTRADA PARA X" já cai no prefixo abaixo)
GENERICOS = {"ESTRADA", "FAZENDA", "CENTRO", "SITIO", "ZONA RURAL"}
PREFIXO_PROPRIEDADE = re.compile(
    r"^(SITIO|FAZENDA|HARAS|CONDOMINIO|ASSOCIACAO|GROTA APOS|RODOVIA|ESTRADA|CHACARA)\b"
)
MIN_ENDERECOS = 5  # comunidades com menos endereços são absorvidas pelos vizinhos
K_VIZINHOS = 9

ESPECIES = {
    "1": "Domicílio particular",
    "2": "Domicílio coletivo",
    "3": "Estabelecimento agropecuário",
    "4": "Estabelecimento de ensino",
    "5": "Estabelecimento de saúde",
    "6": "Estabelecimento de outras finalidades",
    "7": "Edificação em construção",
    "8": "Estabelecimento religioso",
}


def normalizar(txt) -> str:
    if txt is None or (isinstance(txt, float) and np.isnan(txt)):
        return ""
    return re.sub(r"\s+", " ", unidecode(str(txt)).upper()).strip()


def setores() -> gpd.GeoDataFrame:
    s = gpd.read_file(C.ARQ_SETORES, where=f"CD_MUN='{C.COD_MUNICIPIO}'")
    return s[["CD_SETOR", "SITUACAO", "CD_SIT", "CD_DIST", "NM_DIST", "AREA_KM2", "geometry"]]


def distritos(s: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return s.dissolve(by=["CD_DIST", "NM_DIST"], as_index=False)[["CD_DIST", "NM_DIST", "geometry"]]


def municipio(s: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = gpd.GeoDataFrame({"NM_MUN": [C.NOME_MUNICIPIO]}, geometry=[s.union_all()], crs=s.crs)
    return g


def localidades_oficiais() -> gpd.GeoDataFrame:
    g = gpd.read_file(C.ARQ_LOCALIDADES, where=f"CD_MUN='{C.COD_MUNICIPIO}'")
    return g[["CD_LOCALIDADE", "NM_LOCALIDADE", "CT_LOCALIDADE", "geometry"]]


def enderecos(s: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Pontos do CNEFE com a situação (urbana/rural) e o distrito do setor."""
    c = pd.read_csv(C.ARQ_CNEFE, sep=";", dtype=str, encoding="latin1")
    c["CD_SETOR"] = c["COD_SETOR"].str[:15]
    c = c.merge(s.drop(columns="geometry")[["CD_SETOR", "SITUACAO", "NM_DIST"]], on="CD_SETOR", how="left")
    c["LATITUDE"] = c["LATITUDE"].astype(float)
    c["LONGITUDE"] = c["LONGITUDE"].astype(float)
    g = gpd.GeoDataFrame(
        c, geometry=gpd.points_from_xy(c["LONGITUDE"], c["LATITUDE"]), crs=C.CRS_GEO
    )
    # Endereços sem setor (303) caem no setor que os contém
    sem = g["SITUACAO"].isna()
    if sem.any():
        j = gpd.sjoin(g.loc[sem, ["geometry"]], s[["SITUACAO", "NM_DIST", "geometry"]], how="left")
        j = j[~j.index.duplicated()]
        g.loc[sem, "SITUACAO"] = j["SITUACAO"]
        g.loc[sem, "NM_DIST"] = j["NM_DIST"]
    g["ESPECIE"] = g["COD_ESPECIE"].map(ESPECIES)
    return g


def _rotulo_valido(nome: str, rural: bool) -> bool:
    if not nome or nome in GENERICOS or PREFIXO_PROPRIEDADE.match(nome):
        return False
    if rural and nome == normalizar(C.NOME_MUNICIPIO):  # o nome da sede, na zona rural, não diz qual comunidade
        return False
    return True


def gabarito(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Atribui a comunidade real (limpa) a cada endereço. Rural e urbano são tratados à parte."""
    g = g.copy()
    g["ROTULO_ORIGINAL"] = g["DSC_LOCALIDADE"].map(normalizar)
    g["ZONA"] = np.where(g["SITUACAO"] == "Rural", "Rural", "Urbana")
    m = g.to_crs(C.CRS_METRICO)
    xy = np.c_[m.geometry.x, m.geometry.y]
    g["COMUNIDADE"] = None
    g["REATRIBUIDO"] = False

    for zona in ("Rural", "Urbana"):
        idx = np.where(g["ZONA"] == zona)[0]
        rot = g["ROTULO_ORIGINAL"].iloc[idx]
        valido = rot.map(lambda n: _rotulo_valido(n, zona == "Rural"))
        cont = rot[valido].value_counts()
        valido &= rot.map(cont).fillna(0) >= MIN_ENDERECOS
        knn = KNeighborsClassifier(n_neighbors=K_VIZINHOS).fit(xy[idx][valido.values], rot[valido].values)
        final = rot.where(valido, None).to_numpy(dtype=object)
        if (~valido).any():
            final[~valido.values] = knn.predict(xy[idx][~valido.values])
        g.iloc[idx, g.columns.get_loc("COMUNIDADE")] = final
        g.iloc[idx, g.columns.get_loc("REATRIBUIDO")] = ~valido.values

    g["COMUNIDADE"] = g["COMUNIDADE"].str.title()
    return g


def construir():
    s = setores()
    mun = municipio(s)
    C.definir_crs(mun.to_crs(C.CRS_GEO).union_all())  # zona UTM pela posição do município
    distritos(s).to_file(C.INTERIM / "distritos.gpkg")
    mun.to_file(C.INTERIM / "municipio.gpkg")
    s.to_file(C.INTERIM / "setores.gpkg")
    localidades_oficiais().to_file(C.INTERIM / "localidades_oficiais.gpkg")
    g = gabarito(enderecos(s))
    cols = ["COD_UNICO_ENDERECO", "CD_SETOR", "NM_DIST", "ZONA", "ESPECIE", "COD_ESPECIE",
            "NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "NUM_ENDERECO",
            "DSC_ESTABELECIMENTO", "ROTULO_ORIGINAL", "COMUNIDADE", "REATRIBUIDO", "geometry"]
    g[cols].to_file(C.INTERIM / "enderecos_gabarito.gpkg")
    return g


if __name__ == "__main__":
    g = construir()
    r = g[g.ZONA == "Rural"]
    print(f"Endereços: {len(g)} | rurais: {len(r)} | reatribuídos rurais: {r.REATRIBUIDO.sum()}")
    print(f"Comunidades rurais: {r.COMUNIDADE.nunique()} | bairros urbanos: {g[g.ZONA=='Urbana'].COMUNIDADE.nunique()}")
    print(r.groupby(["NM_DIST", "COMUNIDADE"]).size().to_string())
