"""API do Farol (FastAPI): recebe a planilha de UCs afetadas e devolve municípios, comunidades e aviso.

Controller: lê o arquivo (api/leitura.py), valida as linhas (nucleo/planilha.py), busca no banco
a base territorial dos municípios que as coordenadas tocam (banco/base_territorial.py) e chama o
núcleo (nucleo/afetados.py). A planilha fica só em memória e é descartada: nada de número de UC
ou coordenada na resposta, no banco ou no log. Os problemas citam só o número da linha.

Ainda sem login (etapa 7): rode só na própria máquina.
Uso: uv run uvicorn comunidades.api.app:app --host 127.0.0.1 --port 8000
"""

from collections import Counter
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pyproj import Transformer

from .. import distribuidora as dist_
from ..banco import base_territorial as banco
from ..fontes.base_territorial import CRS_BASE
from ..nucleo import idiomas
from ..nucleo.afetados import BaseMunicipio, afetados, municipio_de
from ..nucleo.desligamento import PALAVRAS_POR_SEGUNDO
from ..nucleo.planilha import MAX_LINHAS, PlanilhaInvalida, modelo_csv, validar
from . import leitura

MAX_PROBLEMAS = 200          # problemas listados um a um na resposta (o total vem sempre)
MAX_TEXTO = 40               # data e horário: o que vai no aviso, digitado pelo operador
AVISO_FICTICIO = ("Rede elétrica e clientes fictícios nesta demonstração; território, endereços e "
                  "comunidades reais (IBGE, Censo 2022).")
GEO_PARA_BASE = Transformer.from_crs("EPSG:4674", CRS_BASE, always_xy=True)

app = FastAPI(title="Farol", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
DIST = dist_.carregar()
APRESENTACAO = Path(__file__).resolve().parents[1] / "apresentacao"
TELA = APRESENTACAO / "app"            # a tela (index.html, app.js, app.css)
# A tela só fala com a própria API e só busca de fora os fundos de mapa da Esri
CSP = "; ".join([
    "default-src 'none'", "script-src 'self'", "style-src 'self'", "font-src 'self'", "connect-src 'self'",
    "img-src 'self' data: https://server.arcgisonline.com", "manifest-src 'self'",
    "base-uri 'none'", "form-action 'none'", "frame-ancestors 'none'", "object-src 'none'",
])
SEM_CSP = ("/api/docs", "/api/openapi.json")  # documentação interativa (desenvolvimento): carrega o Swagger de fora


@app.middleware("http")
async def cabecalhos(request, chamar):
    r = await chamar(request)
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Referrer-Policy"] = "no-referrer"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    if not request.url.path.startswith(SEM_CSP):
        r.headers["Content-Security-Policy"] = CSP
    r.headers.setdefault("Cache-Control", "no-store")  # resultados de planilha nunca ficam em cache
    return r


@app.get("/", include_in_schema=False)
def tela() -> FileResponse:
    return FileResponse(TELA / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/config")
def config() -> dict:
    """O que a tela precisa da configuração da distribuidora (nada secreto)."""
    return {"distribuidora": DIST.nome, "telefone": DIST.telefone, "aviso_ficticio": AVISO_FICTICIO,
            "idiomas": {k: v["nome"] for k, v in idiomas.IDIOMAS.items()}, "idioma_padrao": DIST.idioma_padrao,
            "prazo_legal_horas": DIST.prazo_legal_horas, "prazo_vital_dias_uteis": DIST.prazo_vital_dias_uteis,
            "norma": DIST.norma, "palavras_por_segundo": PALAVRAS_POR_SEGUNDO,
            "limites": {"bytes": leitura.MAX_BYTES, "linhas": MAX_LINHAS}}


@app.get("/api/concessao")
def concessao() -> JSONResponse:
    """Contorno dos municípios da concessão (dados públicos do IBGE), para o mapa da tela."""
    return JSONResponse(banco.concessao_geojson(), headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/municipios/{codigo}/comunidades")
def comunidades(codigo: str) -> JSONResponse:
    """Território de cada comunidade do município (dados públicos), para o mapa da tela."""
    if not (len(codigo) == 7 and codigo.isdigit()):
        raise HTTPException(422, "codigo: use o código IBGE do município (7 dígitos).")
    g = banco.comunidades_geojson(codigo)
    if g is None:
        raise HTTPException(404, "Município fora da base da concessão.")
    return JSONResponse(g, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/saude")
def saude() -> dict:
    return {"ok": True, "municipios": len(banco.contornos(CRS_BASE))}


@app.get("/api/modelo-planilha")
def modelo() -> Response:
    # com BOM, para o Excel abrir os acentos certos
    return Response("﻿" + modelo_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="modelo_planilha_farol.csv"'})


def _texto_do_aviso(nome: str, v: str) -> str:
    v = " ".join(str(v).split())
    if not v or len(v) > MAX_TEXTO:
        raise HTTPException(422, f"{nome}: informe de 1 a {MAX_TEXTO} caracteres.")
    return v


def _bases(xy: np.ndarray) -> list[BaseMunicipio]:
    """Só as bases dos municípios que as UCs tocam (os contornos de todos decidem quais são)."""
    todos = banco.contornos(CRS_BASE)
    vazio = np.empty((0, 2))
    leves = [BaseMunicipio(c, n, u, g, vazio, np.array([], dtype=object), np.array([], dtype=object))
             for c, n, u, g in todos]
    usados = sorted(set(municipio_de(xy, leves)) - {-1})
    bases = []
    for i in usados:
        c, n, u, g = todos[i]
        exy, com, dis = banco.enderecos(c, CRS_BASE)
        bases.append(BaseMunicipio(c, n, u, g, exy, com, dis))
    return bases


def _prazo(vital: Counter) -> dict:
    if vital["sim"]:
        regra = f"{DIST.prazo_vital_dias_uteis} dias úteis (há unidades com equipamento vital)"
    elif vital["a_confirmar"]:
        regra = f"{DIST.prazo_vital_dias_uteis} dias úteis até confirmar as unidades sem a informação de equipamento vital"
    else:
        regra = f"{DIST.prazo_legal_horas} horas"
    return {"antecedencia_minima": regra, "norma": DIST.norma, "planejamento_interno_dias": DIST.prazo_interno_dias}


@app.post("/api/avisos")
async def avisos(arquivo: UploadFile = File(...), data: str = Form(...), horario: str = Form(...),
                 idioma: str = Form(idiomas.PADRAO)) -> JSONResponse:
    data, horario = _texto_do_aviso("data", data), _texto_do_aviso("horário", horario)
    if idioma not in idiomas.IDIOMAS:
        raise HTTPException(422, f"idioma: use um de {', '.join(idiomas.IDIOMAS)}.")
    conteudo = await arquivo.read(leitura.MAX_BYTES + 1)
    try:
        p = validar(leitura.ler(conteudo))
    except PlanilhaInvalida as e:
        raise HTTPException(422, str(e)) from None
    finally:
        del conteudo
    v = p.validas
    resposta = {"aviso_ficticio": AVISO_FICTICIO,
                "planilha": {"linhas": p.linhas, "validas": len(v), "total_problemas": len(p.problemas),
                             "problemas_por_motivo": dict(Counter(p.problemas["MOTIVO"])),
                             "problemas": [{"linha": int(l), "motivo": m} for l, m in p.problemas.head(MAX_PROBLEMAS).itertuples(index=False)]},
                "fora_da_concessao": {"ucs": 0, "linhas": []}, "municipios": [], "prazo": _prazo(Counter())}
    if v.empty:
        return JSONResponse(resposta)
    x, y = GEO_PARA_BASE.transform(v["LON"].to_numpy(), v["LAT"].to_numpy())
    xy = np.c_[x, y]
    bases = _bases(xy)
    r = afetados(xy, bases, DIST.regras, data, horario, idioma) if bases else None
    fora = r.fora if r else np.arange(len(v))
    resposta["fora_da_concessao"] = {"ucs": int(len(fora)), "linhas": [int(l) for l in v["LINHA"].iloc[fora[:MAX_PROBLEMAS]]]}
    vital_total = Counter()
    for m in (r.municipios if r else []):
        ucs = v.iloc[m.ucs.index]
        vital = Counter("a_confirmar" if f is None else "sim" if bool(f) else "nao" for f in ucs["VITAL"])
        vital_total += vital
        resposta["municipios"].append({
            "codigo_ibge": m.codigo, "nome": m.nome, "uf": m.uf, "ucs": len(m.ucs),
            "comunidades": [{"nome": c.COMUNIDADE_PREVISTA, "distrito": c.DISTRITO, "afetadas": int(c.UC_AFETADAS),
                             "total": int(c.UC_TOTAL), "parcial": bool(c.PARCIAL), "fragmento": bool(c.FRAGMENTO),
                             "confianca": round(float(c.CONFIANCA), 2)} for c in m.comunidades.itertuples()],
            "aviso": m.aviso, "segundos": m.segundos,
            "equipamento_vital": {k: vital[k] for k in ("sim", "nao", "a_confirmar")},
            # só contagens; a classe é texto livre da planilha, então vai cortada
            "classes": dict(Counter((c or "não informada")[:MAX_TEXTO] for c in ucs["CLASSE"])),
        })
    resposta["prazo"] = _prazo(vital_total)
    return JSONResponse(resposta)


# Arquivos da tela: o app, o Leaflet e as fontes embutidas no projeto (vendor/) e o logo. Nada de CDN.
app.mount("/assets/app", StaticFiles(directory=TELA), name="app")
app.mount("/assets/vendor", StaticFiles(directory=APRESENTACAO / "vendor"), name="vendor")
app.mount("/assets/marca", StaticFiles(directory=APRESENTACAO / "marca"), name="marca")
