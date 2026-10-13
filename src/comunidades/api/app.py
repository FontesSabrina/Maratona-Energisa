"""API do Farol (FastAPI): recebe a planilha de UCs afetadas e devolve municípios, comunidades e aviso.

Controller: lê o arquivo (api/leitura.py), valida as linhas (nucleo/planilha.py), busca no banco
a base territorial dos municípios que as coordenadas tocam (banco/base_territorial.py) e chama o
núcleo (nucleo/afetados.py). A planilha fica só em memória e é descartada: nada de número de UC
na resposta, no banco ou no log, e nada de coordenada no banco ou no log. Os problemas citam só o
número da linha. A resposta do envio traz os pontos das UCs (só latitude, longitude e comunidade,
sem o número) para o mapa de quem enviou; eles não entram no histórico.

Toda rota, menos /api/saude e /api/entrar, exige login (api/acesso.py), e a permissão é conferida
no servidor. Cada planilha processada fica no histórico da empresa só como agregado.
Uso: uv run uvicorn comunidades.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
"""

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pyproj import Transformer

from .. import distribuidora as dist_
from .. import senhas
from ..config import sem_acento
from ..apresentacao import audio
from ..banco import acesso as banco_acesso
from ..banco import base_territorial as banco
from ..banco import rede as banco_rede
from ..fontes.base_territorial import CRS_BASE
from ..nucleo import idiomas, painel
from ..nucleo.afetados import BaseMunicipio, afetados, municipio_de
from ..nucleo.desligamento import PALAVRAS_POR_SEGUNDO, aviso_antigo_de_locais, locais_de
from ..nucleo.planilha import MAX_LINHAS, PlanilhaInvalida, modelo_csv, validar
from . import leitura
from .acesso import PRODUCAO, exigir, rotas, usuario_atual
from .proxy import ProxyConfiavel

MAX_PROBLEMAS = 200          # problemas listados um a um na resposta (o total vem sempre)
MAX_TEXTO = 40               # data e horário: o que vai no aviso, digitado pelo operador
CASAS_PONTO = 5              # casas decimais dos pontos no mapa (cerca de 1 m)
# FAROL_AUDIO=0 desliga o áudio do aviso (o plano gratuito do Render não tem memória para a voz)
AUDIO = os.environ.get("FAROL_AUDIO", "1") != "0"
AVISO_FICTICIO = ("Rede elétrica e clientes fictícios nesta demonstração; território, endereços e "
                  "comunidades reais (IBGE, Censo 2022).")
BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
MAX_AVISOS_PAINEL = 5000      # avisos considerados no dashboard (os mais recentes)
GEO_PARA_BASE = Transformer.from_crs("EPSG:4674", CRS_BASE, always_xy=True)

# em produção, sem a documentação interativa (é a única parte sem CSP: carrega o Swagger de fora)
app = FastAPI(title="Farol", version="0.1.0", docs_url=None if PRODUCAO else "/api/docs",
              openapi_url=None if PRODUCAO else "/api/openapi.json", redoc_url=None)
DIST = dist_.carregar()
app.include_router(rotas)
if PRODUCAO:  # IP e esquema de quem acessa, pelo proxy do Render (api/proxy.py)
    app.add_middleware(ProxyConfiavel)


@app.exception_handler(senhas.Ocupado)
def _ocupado(request, erro: senhas.Ocupado) -> JSONResponse:
    """Hashes de senha demais ao mesmo tempo (memória do servidor): recusa e pede para tentar de novo."""
    return JSONResponse({"detail": str(erro)}, status_code=503, headers={"Retry-After": "5"})


APRESENTACAO = Path(__file__).resolve().parents[1] / "apresentacao"
TELA = APRESENTACAO / "app"            # a tela (index.html, app.js, app.css)
# A tela só fala com a própria API e só busca de fora os fundos de mapa da Esri
CSP = "; ".join([
    "default-src 'none'", "script-src 'self'", "style-src 'self'", "font-src 'self'", "connect-src 'self'",
    "img-src 'self' data: https://server.arcgisonline.com", "manifest-src 'self'",
    "media-src 'self' blob:",  # o tocador do áudio do aviso (o MP3 vem da API e toca de um blob local)
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
    if PRODUCAO:  # só HTTPS daqui para a frente (o Render serve em HTTPS)
        r.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return r


@app.get("/", include_in_schema=False)
def tela() -> FileResponse:
    return FileResponse(TELA / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/config")
def config(u: dict = Depends(usuario_atual)) -> dict:
    """O que a tela precisa da configuração da distribuidora (nada secreto)."""
    return {"distribuidora": DIST.nome, "telefone": DIST.telefone, "aviso_ficticio": AVISO_FICTICIO,
            "idiomas": {k: v["nome"] for k, v in idiomas.IDIOMAS.items()}, "idioma_padrao": DIST.idioma_padrao,
            "prazo_legal_horas": DIST.prazo_legal_horas, "prazo_vital_dias_uteis": DIST.prazo_vital_dias_uteis,
            "norma": DIST.norma, "palavras_por_segundo": PALAVRAS_POR_SEGUNDO,
            "limites": {"bytes": leitura.MAX_BYTES, "linhas": MAX_LINHAS}, "audio": AUDIO}


@app.get("/api/concessao")
def concessao(u: dict = Depends(usuario_atual)) -> JSONResponse:
    """Contorno dos municípios da concessão (dados públicos do IBGE), para o mapa da tela."""
    return JSONResponse(banco.concessao_geojson(), headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/municipios/{codigo}/comunidades")
def comunidades(codigo: str, u: dict = Depends(usuario_atual)) -> JSONResponse:
    """Território de cada comunidade do município (dados públicos), para o mapa da tela."""
    if not (len(codigo) == 7 and codigo.isdigit()):
        raise HTTPException(422, "codigo: use o código IBGE do município (7 dígitos).")
    g = banco.comunidades_geojson(codigo)
    if g is None:
        raise HTTPException(404, "Município fora da base da concessão.")
    return JSONResponse(g, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/municipios/{codigo}/rede")
def rede(codigo: str, u: dict = Depends(usuario_atual)) -> JSONResponse:
    """Rede elétrica FICTÍCIA do município (demonstração): média tensão, subestação, chaves e trafos."""
    if not (len(codigo) == 7 and codigo.isdigit()):
        raise HTTPException(422, "codigo: use o código IBGE do município (7 dígitos).")
    r = banco_rede.rede_mapa(codigo)
    if r is None:
        raise HTTPException(404, "Município sem rede fictícia no banco.")
    return JSONResponse(r, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/saude")
def saude() -> dict:
    return {"ok": True, "municipios": len(banco.contornos(CRS_BASE))}


@app.get("/api/modelo-planilha")
def modelo(u: dict = Depends(usuario_atual)) -> Response:
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


def _pontos(ucs, comunidades=None, ordem=()) -> list[list]:
    """Pontos das UCs para o mapa de quem enviou a planilha: [lat, lon] ou [lat, lon, comunidade].
    Nunca o número da UC; não vão para o histórico (_guardar escolhe os campos que grava)."""
    lat, lon = ucs["LAT"].round(CASAS_PONTO).tolist(), ucs["LON"].round(CASAS_PONTO).tolist()
    if comunidades is None:
        return [[a, o] for a, o in zip(lat, lon)]
    posicao = {nome: i for i, nome in enumerate(ordem)}
    return [[a, o, posicao.get(c, -1)] for a, o, c in zip(lat, lon, comunidades)]


def _aviso_hoje(locais, data: str, horario: str) -> dict | None:
    """O aviso como é hoje (imóvel por imóvel, rua por rua), com os locais citados, as palavras e o tempo no ar.
    Pode listar imóveis e ruas (é o comunicado público que já vai ao rádio); nunca pessoas, UCs nem coordenadas.
    None se nenhuma UC do município tem local (não há o que comparar)."""
    if not locais_de(locais):
        return None
    texto = aviso_antigo_de_locais(locais, data, horario, DIST.regras)
    palavras = len(texto.split())
    return {"texto": texto, "locais": len(locais_de(locais)), "palavras": palavras,
            "segundos": round(palavras / PALAVRAS_POR_SEGUNDO)}


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
                 idioma: str = Form(idiomas.PADRAO), u: dict = Depends(exigir("gerar_aviso"))) -> JSONResponse:
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
                "fora_da_concessao": {"ucs": 0, "linhas": []}, "municipios": [], "prazo": _prazo(Counter()),
                "pontos_fora": []}
    if v.empty:
        return JSONResponse(_guardar(resposta, u, data, horario, idioma))
    x, y = GEO_PARA_BASE.transform(v["LON"].to_numpy(), v["LAT"].to_numpy())
    xy = np.c_[x, y]
    bases = _bases(xy)
    r = afetados(xy, bases, DIST.regras, data, horario, idioma) if bases else None
    fora = r.fora if r else np.arange(len(v))
    resposta["fora_da_concessao"] = {"ucs": int(len(fora)), "linhas": [int(l) for l in v["LINHA"].iloc[fora[:MAX_PROBLEMAS]]]}
    resposta["pontos_fora"] = _pontos(v.iloc[fora])
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
            # o aviso de hoje (fazenda a fazenda), se a planilha trouxe a coluna local: só para o comparativo
            "hoje": _aviso_hoje(ucs["LOCAL"], data, horario) if p.tem_local else None,
            # [lat, lon, posição da comunidade na lista acima (-1 = sem comunidade)], sem o número da UC
            "pontos": _pontos(ucs, m.ucs["COMUNIDADE_PREVISTA"], [c.COMUNIDADE_PREVISTA for c in m.comunidades.itertuples()]),
            "equipamento_vital": {k: vital[k] for k in ("sim", "nao", "a_confirmar")},
            # só contagens; a classe é texto livre da planilha, então vai cortada
            "classes": dict(Counter((c or "não informada")[:MAX_TEXTO] for c in ucs["CLASSE"])),
        })
    resposta["prazo"] = _prazo(vital_total)
    return JSONResponse(_guardar(resposta, u, data, horario, idioma))


def _guardar(resposta: dict, u: dict, data: str, horario: str, idioma: str) -> dict:
    """Grava no histórico da empresa só o agregado (sem as linhas com problema) e devolve a resposta com o id."""
    p = resposta["planilha"]
    resumo = {"linhas": p["linhas"], "validas": p["validas"], "problemas": p["total_problemas"],
              "fora_da_concessao": resposta["fora_da_concessao"]["ucs"], "prazo": resposta["prazo"]}
    # do aviso de hoje, só as contagens (o texto lista imóveis e ruas e não precisa ficar guardado)
    municipios = [{**{k: m[k] for k in ("codigo_ibge", "nome", "uf", "ucs", "comunidades", "aviso", "segundos", "equipamento_vital")},
                   "hoje": {k: m["hoje"][k] for k in ("locais", "palavras", "segundos")} if m.get("hoje") else None}
                  for m in resposta["municipios"]]
    resposta["id"] = banco_acesso.gravar_aviso(u["empresa_id"], u["id"], data, horario, idioma, resumo, municipios)
    banco_acesso.registrar("gerou aviso", f"aviso {resposta['id']}: {', '.join(m['nome'] for m in municipios) or 'nenhum município'}"
                           f" ({p['linhas']} linhas)", u["id"], u["empresa_id"])
    return resposta


# ---------- Histórico de avisos da empresa ----------
class TextoFinal(BaseModel):
    texto: str


class PedidoAudio(BaseModel):
    # o limite do texto é conferido de novo, com o tamanho de cada caso, ao gerar (audio.mp3)
    texto: str = Field(max_length=audio.MAX_CARACTERES_COMPARATIVO)
    idioma: str = Field(idiomas.PADRAO, max_length=10)
    municipio: str = Field("", max_length=100)   # só para o nome do arquivo e o registro
    comparativo: bool = False  # o aviso de hoje no comparativo: pode ser bem mais longo


@app.post("/api/audio")
def gerar_audio(dados: PedidoAudio, u: dict = Depends(exigir("gerar_aviso"))) -> Response:
    """MP3 do aviso falado (voz sintetizada no próprio servidor, sem enviar o texto para fora)."""
    if not AUDIO:
        raise HTTPException(503, "O áudio do aviso está desligado neste servidor.")
    try:
        mp3, segundos = audio.mp3(dados.texto, dados.idioma,
                                  max_caracteres=audio.MAX_CARACTERES_COMPARATIVO if dados.comparativo else audio.MAX_CARACTERES)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    municipio = "".join(ch for ch in dados.municipio if ch.isalnum() or ch in " -")[:60].strip() or "aviso"
    arquivo = "-".join(sem_acento(municipio).lower().encode("ascii", "ignore").decode().split()) or "aviso"
    banco_acesso.registrar("gerou o áudio do aviso" + (" de hoje (comparativo)" if dados.comparativo else ""),
                           f"{municipio}, {segundos:.0f} s", u["id"], u["empresa_id"])
    return Response(mp3, media_type="audio/mpeg", headers={
        "Content-Disposition": f'attachment; filename="farol-aviso-{arquivo}.mp3"',
        "X-Duracao-Segundos": f"{segundos:.1f}"})


def _aviso_publico(a: dict) -> dict:
    return {"id": a["id"], "criado_em": a["criado_em"].isoformat(), "data": a["data"], "horario": a["horario"],
            "idioma": a["idioma"], "usuario": a["usuario"], "resumo": a["resumo"], "municipios": a["municipios"]}


@app.get("/api/historico")
def historico(u: dict = Depends(exigir("ver_historico"))) -> dict:
    return {"avisos": [_aviso_publico(a) for a in banco_acesso.avisos(u["empresa_id"])]}


@app.get("/api/historico/{id_}")
def historico_um(id_: int, u: dict = Depends(exigir("ver_historico"))) -> dict:
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    return _aviso_publico(a)


@app.get("/api/painel")
def dashboard(u: dict = Depends(exigir("ver_historico"))) -> dict:
    """Dashboard da empresa: só agregados do histórico (nucleo/painel.py), no horário de Brasília."""
    avisos = [{**a, "criado_em": a["criado_em"].astimezone(BRASILIA)}
              for a in banco_acesso.avisos(u["empresa_id"], MAX_AVISOS_PAINEL)]
    return painel.resumir(avisos, datetime.now(BRASILIA).date())


@app.put("/api/historico/{id_}/municipios/{codigo}/texto")
def guardar_texto_final(id_: int, codigo: str, dados: TextoFinal, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """O texto que foi para a rádio (depois da edição), gravado ao baixar o PDF ou copiar."""
    texto = dados.texto.strip()
    if not 1 <= len(texto) <= 3000:
        raise HTTPException(422, "Texto do aviso: de 1 a 3.000 caracteres.")
    if not banco_acesso.texto_final(id_, u["empresa_id"], codigo, texto):
        raise HTTPException(404, "Aviso ou município não encontrado nesta empresa.")
    banco_acesso.registrar("guardou o texto final", f"aviso {id_}, município {codigo}", u["id"], u["empresa_id"])
    return {"ok": True}


# Arquivos da tela: o app, o Leaflet e as fontes embutidas no projeto (vendor/) e o logo. Nada de CDN.
app.mount("/assets/app", StaticFiles(directory=TELA), name="app")
app.mount("/assets/vendor", StaticFiles(directory=APRESENTACAO / "vendor"), name="vendor")
app.mount("/assets/marca", StaticFiles(directory=APRESENTACAO / "marca"), name="marca")
