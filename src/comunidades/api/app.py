"""API do Farol (FastAPI): recebe a planilha de UCs afetadas e devolve municípios, comunidades e aviso.

Controller: lê o arquivo (api/leitura.py), traduz as linhas para o JSON validado (nucleo/planilha.py),
confere de novo por uma rotina independente (api/conferencia.py), busca no banco a base territorial
dos municípios que as coordenadas tocam (banco/base_territorial.py) e chama o núcleo
(nucleo/afetados.py). A planilha fica só em memória e é descartada: nada de número de UC na resposta,
no banco ou no log, e nada de coordenada no banco ou no log. Os problemas citam só o número da linha.
A resposta traz os pontos das UCs (só latitude, longitude e comunidade, sem o número) para o mapa de
quem enviou; eles não entram no histórico.

Dois passos: /api/planilha (Conferir) devolve a conferência, as travas (nucleo/travas.py) e o pacote
assinado (api/pacote.py); /api/avisos (Gerar) só aceita esse pacote, com a confirmação humana, e grava.

Toda rota, menos /api/saude e /api/entrar, exige login (api/acesso.py), e a permissão é conferida
no servidor. Cada planilha processada fica no histórico da empresa só como agregado.
Uso: uv run uvicorn comunidades.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
"""

import functools
import hashlib
import logging
import secrets
import time
import traceback
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import shapely
from pyproj import Transformer

from .. import senhas
from ..config import sem_acento
from ..apresentacao import audio
from ..banco import acesso as banco_acesso
from ..banco import base_territorial as banco
from ..banco import rede as banco_rede
from ..banco import radios as banco_radios
from ..banco import relatorios as banco_relatorios
from ..fontes.base_territorial import CRS_BASE
from .. import correio
from ..nucleo import agrupamento, auditoria, esquema_planilha, idiomas, mensagem, painel, travas
from ..nucleo import tipos_desligamento as tipos
from ..nucleo.afetados import BaseMunicipio, afetados, municipio_de
from ..nucleo.desligamento import PALAVRAS_POR_SEGUNDO, aviso_antigo_de_locais, locais_de
from ..nucleo import planilha
from ..nucleo.acesso import PERFIS
from ..nucleo.coordenadas import Area
from ..nucleo.motivos import TEXTOS, Motivo
from ..nucleo.planilha import MAX_LINHAS, PlanilhaInvalida, modelo_csv
from . import conferencia, leitura
from . import pacote as pacote_
from .comum import AUDIO, AVISO_FICTICIO, BRASILIA, DIST, MAX_TEXTO, config_empresa, segundos
from .comum import texto_do_aviso as _texto_do_aviso
from .radio import rotas as radio_rotas
from .relatorios import painel_do_mes
from .relatorios import rotas as relatorio_rotas
from .acesso import PRODUCAO, exigir, rotas, usuario_atual
from .proxy import ProxyConfiavel

MAX_PROBLEMAS = 200          # problemas listados um a um na resposta (o total vem sempre)
CASAS_PONTO = 5              # casas decimais dos pontos no mapa (cerca de 1 m)
MAX_AVISOS_PAINEL = 5000      # avisos considerados no dashboard (os mais recentes)
GEO_PARA_BASE = Transformer.from_crs("EPSG:4674", CRS_BASE, always_xy=True)

# em produção, sem a documentação interativa (é a única parte sem CSP: carrega o Swagger de fora)
app = FastAPI(title="Farol", version="0.1.0", docs_url=None if PRODUCAO else "/api/docs",
              openapi_url=None if PRODUCAO else "/api/openapi.json", redoc_url=None)
app.include_router(rotas)
app.include_router(radio_rotas)
app.include_router(relatorio_rotas)
if PRODUCAO:  # IP e esquema de quem acessa, pelo proxy do Render (api/proxy.py)
    app.add_middleware(ProxyConfiavel)


_log = logging.getLogger("farol.api")


@app.exception_handler(Exception)
def _erro_inesperado(request, erro: Exception) -> JSONResponse:
    """Erro não previsto: nada é gerado nem gravado (o histórico só é gravado no fim de tudo) e a
    pessoa recebe um código para o suporte. O log técnico leva só o tipo do erro e onde ele ocorreu
    (arquivo e linha), nunca a mensagem nem valores: assim nenhum dado da planilha vai para o log."""
    codigo = f"ERR-{secrets.token_hex(3).upper()}"
    onde = " <- ".join(f"{Path(q.filename).name}:{q.lineno}" for q in traceback.extract_tb(erro.__traceback__)[-4:][::-1])
    _log.error("%s %s %s em %s", codigo, request.url.path, type(erro).__name__, onde)
    return JSONResponse({"detail": f"Ocorreu um erro e nada foi gerado (código {codigo})."}, status_code=500)


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
    if not request.url.path.startswith(SEM_CSP) and "content-security-policy" not in r.headers:
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
            "limites": {"bytes": leitura.MAX_BYTES, "linhas": MAX_LINHAS}, "audio": AUDIO,
            "tipos": tipos.ROTULOS, "tipo_padrao": tipos.PADRAO, "max_outro": tipos.MAX_OUTRO, "email": correio.ligado()}


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
    banco_acesso.registrar("baixou o modelo da planilha", "modelo_planilha_farol.csv", u["id"], u["empresa_id"])
    # com BOM, para o Excel abrir os acentos certos
    return Response("﻿" + modelo_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="modelo_planilha_farol.csv"'})


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


def _prazo(vital: Counter, cfg: dict) -> dict:
    if vital["sim"]:
        regra = f"{DIST.prazo_vital_dias_uteis} dias úteis (há unidades com equipamento vital)"
    elif vital["a_confirmar"]:
        regra = f"{DIST.prazo_vital_dias_uteis} dias úteis até confirmar as unidades sem a informação de equipamento vital"
    else:
        regra = f"{DIST.prazo_legal_horas} horas"
    return {"antecedencia_minima": regra, "norma": DIST.norma, "planejamento_interno_dias": cfg["antecedencia_dias"]}


@functools.lru_cache(maxsize=1)
def _area() -> Area:
    """A área da concessão (os contornos dos municípios do banco) com a margem de 50 m, para o tradutor."""
    return Area(shapely.union_all([g for _, _, _, g in banco.contornos("EPSG:4674")]))


def _parametros(cfg: dict) -> planilha.Parametros:
    """Os parâmetros do tradutor: o fuso UTM é o da empresa; o resto, o da distribuidora."""
    c = DIST.planilha
    return planilha.Parametros(dentro=_area(), epsg_utm=cfg["epsg_utm"], isolado_km=c.ponto_isolado_km,
                               muitas_ucs=c.muitas_ucs_mesma_coordenada)


def _nome_arquivo(nome: str | None) -> str:
    """O nome do arquivo enviado, limpo: sem pasta, sem caracteres de controle, até 100 caracteres."""
    base = str(nome or "planilha").replace("\\", "/").rsplit("/", 1)[-1]
    return (planilha.limpar(base) or "planilha")[:100]


def _traduzir(conteudo: bytes, nome: str | None, aba: str | None, u: dict):
    """Arquivo -> JSON padronizado validado (nucleo/planilha.montar). O arquivo não é guardado."""
    tabela = leitura.ler_tabela(conteudo, aba)
    if not tabela.linhas:
        raise PlanilhaInvalida("A planilha não tem nenhuma linha de dados.")
    modelo = planilha.montar(
        tabela.campos, tabela.cabecalho, tabela.linhas, _parametros(config_empresa(u["empresa_id"])),
        arquivo={"nome": _nome_arquivo(nome), "sha256": hashlib.sha256(conteudo).hexdigest(), "formato": tabela.formato,
                 "aba": tabela.aba, "colunas_ignoradas": tabela.colunas_ignoradas},
        empresa=(u.get("empresa_nome") or "")[:120], gerado_em=datetime.now(BRASILIA).strftime("%Y-%m-%dT%H:%M"),
        gerado_por=f"{u['nome']} ({PERFIS[u['perfil']]})"[:160])
    try:   # dupla conferência: rotina independente relê o arquivo (api/conferencia.py)
        conferencia.conferir(conteudo, modelo)
    except conferencia.Divergencia as e:
        banco_acesso.registrar("planilha bloqueada pela conferência independente", str(e)[:200], u["id"], u["empresa_id"])
        raise PlanilhaInvalida(f"Nada foi gerado: {e}. Confira a planilha e envie de novo.") from None
    return modelo


def _traducao(m) -> dict:
    """O que a tela mostra da tradução: arquivo, colunas reconhecidas, resumo e o que foi corrigido (sem UC)."""
    return {"arquivo": {k: getattr(m.arquivo, k) for k in ("nome", "formato", "aba", "linhas", "colunas_ignoradas")},
            "colunas": list(m.colunas), "resumo": m.resumo.model_dump(), "versao": m.tradutor,
            "corrigidas": [{"linha": pt.linha, "codigo": pt.correcao.value, "correcao": TEXTOS[pt.correcao]}
                           for pt in m.pontos if pt.status == "corrigida"][:MAX_PROBLEMAS],
            "avisos": [{"linha": pt.linha, "avisos": [a.value for a in pt.avisos]}
                       for pt in m.pontos if pt.avisos][:MAX_PROBLEMAS],
            "textos": {k.value: v for k, v in TEXTOS.items()}}


LIMITE_ENVIOS, JANELA_ENVIOS = 20, 3600       # planilhas por usuário por hora
_envios: dict[int, deque] = defaultdict(deque)


def _limite_envios(usuario_id: int) -> None:
    """No máximo LIMITE_ENVIOS planilhas por usuário em JANELA_ENVIOS segundos (cada uma custa CPU e memória)."""
    agora, fila = time.monotonic(), _envios[usuario_id]
    while fila and agora - fila[0] > JANELA_ENVIOS:
        fila.popleft()
    if len(fila) >= LIMITE_ENVIOS:
        raise HTTPException(429, f"Limite de {LIMITE_ENVIOS} planilhas por hora atingido. Tente de novo mais tarde.")
    fila.append(agora)


class PedidoAviso(BaseModel):
    """2º passo: o pacote assinado da conferência, a data e o horário, a confirmação e a justificativa."""
    pacote: str = Field(max_length=pacote_.MAX_PACOTE)
    data: str = Field(max_length=200)
    horario: str = Field(max_length=200)
    idioma: str = Field(idiomas.PADRAO, max_length=10)
    conferi: bool = False
    justificativa: str | None = Field(None, max_length=2000)
    tipo: str = Field(tipos.PADRAO, max_length=40)
    tipo_outro: str | None = Field(None, max_length=1000)


def _formulario(data: str, horario: str, idioma: str) -> tuple[str, str, str]:
    data, horario = _texto_do_aviso("data", data), _texto_do_aviso("horário", horario)
    if idioma not in idiomas.IDIOMAS:
        raise HTTPException(422, f"idioma: use um de {', '.join(idiomas.IDIOMAS)}.")
    return data, horario, idioma


def _motivo(tipo: str, outro: str | None) -> tuple[str, str]:
    """O tipo de desligamento (lista fechada ou "Outro" curto e sem dado pessoal) e o texto do motivo."""
    try:
        return tipos.motivo(tipo, outro)
    except ValueError as e:
        raise HTTPException(422, f"Tipo de desligamento: {e}") from None


class _PedeAba(Exception):
    def __init__(self, mensagem: str, abas: list[str]):
        super().__init__(mensagem)
        self.abas = abas


@app.exception_handler(_PedeAba)
def _pede_aba(request, e: _PedeAba) -> JSONResponse:
    """Mais de uma aba serve: 409 com a lista, para a pessoa escolher."""
    return JSONResponse({"detail": str(e), "abas": e.abas}, status_code=409)


async def _ler_e_traduzir(arquivo: UploadFile, aba: str | None, u: dict):
    """O arquivo enviado -> JSON validado; o arquivo sai da memória aqui. 409 pede a aba; 422 recusa."""
    _limite_envios(u["id"])
    conteudo = await arquivo.read(leitura.MAX_BYTES + 1)
    try:
        return _traduzir(conteudo, arquivo.filename, aba or None, u)
    except leitura.EscolhaDeAba as e:
        raise _PedeAba(str(e), e.abas) from None
    except PlanilhaInvalida as e:
        raise HTTPException(422, str(e)) from None
    finally:
        del conteudo


def _resultado(modelo, data: str, horario: str, idioma: str, cfg: dict) -> dict:
    """Do JSON validado (nunca da planilha bruta): municípios, comunidades, avisos, pontos e as travas."""
    v = planilha.validas(modelo)
    rejeitadas = [pt for pt in modelo.pontos if pt.status == "rejeitada"]
    fora_planilha = [pt for pt in rejeitadas if pt.motivo == Motivo.FORA_DA_CONCESSAO]
    resposta = {"aviso_ficticio": AVISO_FICTICIO,
                "planilha": {"linhas": modelo.resumo.total, "validas": len(v), "total_problemas": len(rejeitadas),
                             "problemas_por_motivo": dict(Counter(TEXTOS[pt.motivo] for pt in rejeitadas)),
                             "problemas": [{"linha": pt.linha, "codigo": pt.motivo.value, "motivo": TEXTOS[pt.motivo]}
                                           for pt in rejeitadas[:MAX_PROBLEMAS]]},
                "traducao": _traducao(modelo),
                "fora_da_concessao": {"ucs": len(fora_planilha), "linhas": [pt.linha for pt in fora_planilha[:MAX_PROBLEMAS]]},
                "municipios": [], "prazo": _prazo(Counter(), cfg),
                "pontos_fora": [[round(pt.lat, CASAS_PONTO), round(pt.lon, CASAS_PONTO)] for pt in fora_planilha],
                # as corrigidas, com cor própria no mapa (só latitude e longitude, sem a UC)
                "pontos_corrigidos": [[round(pt.lat, CASAS_PONTO), round(pt.lon, CASAS_PONTO)]
                                      for pt in modelo.pontos if pt.status == "corrigida"]}
    linhas_fora, por_municipio = set(), {}
    if not v.empty:
        x, y = GEO_PARA_BASE.transform(v["LON"].to_numpy(), v["LAT"].to_numpy())
        xy = np.c_[x, y]
        bases = _bases(xy)
        r = afetados(xy, bases, DIST.regras, data, horario, idioma) if bases else None
        fora = r.fora if r else np.arange(len(v))
        if len(fora):   # dentro da área com a margem, mas fora dos contornos dos municípios (na divisa da concessão)
            linhas_fora = {int(l) for l in v["LINHA"].iloc[fora]}
            resposta["fora_da_concessao"]["ucs"] += int(len(fora))
            resposta["fora_da_concessao"]["linhas"] = sorted(resposta["fora_da_concessao"]["linhas"] + sorted(linhas_fora))[:MAX_PROBLEMAS]
            resposta["pontos_fora"] += _pontos(v.iloc[fora])
        vital_total = Counter()
        for m in (r.municipios if r else []):
            ucs = v.iloc[m.ucs.index]
            por_municipio[f"{m.nome}/{m.uf}"] = [int(l) for l in ucs["LINHA"]]
            vital = Counter("a_confirmar" if f is None else "sim" if bool(f) else "nao" for f in ucs["VITAL"])
            vital_total += vital
            resposta["municipios"].append({
                "codigo_ibge": m.codigo, "nome": m.nome, "uf": m.uf, "ucs": len(m.ucs),
                "comunidades": [{"nome": c.COMUNIDADE_PREVISTA, "distrito": c.DISTRITO, "afetadas": int(c.UC_AFETADAS),
                                 "total": int(c.UC_TOTAL), "parcial": bool(c.PARCIAL), "fragmento": bool(c.FRAGMENTO),
                                 "confianca": round(float(c.CONFIANCA), 2)} for c in m.comunidades.itertuples()],
                "aviso": m.aviso, "segundos": m.segundos,
                # o aviso de hoje (fazenda a fazenda), se a planilha trouxe a coluna local: só para o comparativo
                "hoje": _aviso_hoje(ucs["LOCAL"], data, horario) if "local" in modelo.colunas else None,
                # [lat, lon, posição da comunidade na lista acima (-1 = sem comunidade)], sem o número da UC
                "pontos": _pontos(ucs, m.ucs["COMUNIDADE_PREVISTA"], [c.COMUNIDADE_PREVISTA for c in m.comunidades.itertuples()]),
                "equipamento_vital": {k: vital[k] for k in ("sim", "nao", "a_confirmar")},
                # só contagens; a classe é texto livre da planilha, então vai cortada
                "classes": dict(Counter((c or "não informada")[:MAX_TEXTO] for c in ucs["CLASSE"])),
            })
        resposta["prazo"] = _prazo(vital_total, cfg)
    # por transformador e por circuito (só os códigos da rede e contagens), se a planilha trouxe as colunas
    resposta["rede"] = {campo: agrupamento.por_codigo(v[campo.upper()].tolist()) for campo in ("circuito", "transformador")
                        if campo in modelo.colunas}
    ms = resposta["municipios"]
    resposta["conferencia"] = {
        "vital_bloqueio": travas.vital_bloqueio(modelo, linhas_fora),
        "rejeicao": travas.rejeicao(modelo, cfg["limite_rejeicao"]),
        "suspeitos": travas.suspeitos(modelo, por_municipio),
        "arquivo": modelo.arquivo.nome, "sha256": modelo.arquivo.sha256,
        "numeros": {"clientes": sum(m["ucs"] for m in ms), "municipios": len(ms),
                    "comunidades": sum(len(m["comunidades"]) for m in ms),
                    "equipamento_vital": sum(m["equipamento_vital"]["sim"] for m in ms),
                    "vital_a_confirmar": sum(m["equipamento_vital"]["a_confirmar"] for m in ms),
                    "corrigidas": modelo.resumo.corrigidas, "rejeitadas": modelo.resumo.rejeitadas,
                    "fora_da_concessao": resposta["fora_da_concessao"]["ucs"]}}
    return resposta


@app.post("/api/planilha")
async def conferir_planilha(arquivo: UploadFile = File(...), data: str = Form(...), horario: str = Form(...),
                            idioma: str = Form(idiomas.PADRAO), aba: str | None = Form(None, max_length=leitura.MAX_NOME_ABA),
                            tipo: str = Form(tipos.PADRAO, max_length=40), tipo_outro: str | None = Form(None, max_length=1000),
                            u: dict = Depends(exigir("gerar_aviso"))) -> JSONResponse:
    """1º passo (Conferir): traduz a planilha e mostra o resultado e as travas. Nada vai para o histórico.
    Devolve o pacote assinado (UCs opacas, 15 minutos) que o 2º passo usa para gerar o aviso."""
    data, horario, idioma = _formulario(data, horario, idioma)
    tipo, motivo = _motivo(tipo, tipo_outro)
    modelo = await _ler_e_traduzir(arquivo, aba, u)
    cfg = config_empresa(u["empresa_id"])
    resposta = _resultado(modelo, data, horario, idioma, cfg)
    resposta["desligamento"] = {"tipo": tipo, "rotulo": tipos.ROTULOS[tipo], "motivo": motivo}
    _mensagens(resposta["municipios"], cfg, data, horario, idioma, motivo)
    _alerta_repeticao(resposta, u, cfg)
    resposta["pacote"], vence = pacote_.assinar(travas.ucs_opacas(modelo), u["id"], u["empresa_id"])
    resposta["pacote_vence"] = datetime.fromtimestamp(vence, BRASILIA).isoformat(timespec="seconds")
    r = modelo.resumo
    banco_acesso.registrar("importou planilha", f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256}): {r.total} linhas, "
                           f"{r.ok} ok, {r.corrigidas} corrigidas, {r.rejeitadas} rejeitadas", u["id"], u["empresa_id"])
    return JSONResponse(resposta)


@app.post("/api/avisos")
def gerar_aviso(dados: PedidoAviso, u: dict = Depends(exigir("gerar_aviso"))) -> JSONResponse:
    """2º passo (Gerar aviso): só com o pacote da conferência válido, a caixa "Conferi" marcada, nenhuma
    trava de equipamento vital e, acima do limite de rejeição, a justificativa. Grava no histórico."""
    data, horario, idioma = _formulario(dados.data, dados.horario, dados.idioma)
    tipo, motivo = _motivo(dados.tipo, dados.tipo_outro)
    try:
        modelo = pacote_.abrir(dados.pacote, u["id"], u["empresa_id"])
    except pacote_.PacoteRecusado as e:
        raise HTTPException(422, str(e)) from None
    cfg = config_empresa(u["empresa_id"])
    resposta = _resultado(modelo, data, horario, idioma, cfg)
    _mensagens(resposta["municipios"], cfg, data, horario, idioma, motivo)
    rep = _alerta_repeticao(resposta, u, cfg)
    c, arq = resposta["conferencia"], f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256})"
    problema = travas.problema_para_gerar(c, dados.conferi, dados.justificativa)
    if problema:
        if c["vital_bloqueio"]:
            banco_acesso.registrar("geração bloqueada (equipamento vital)", f"{arq}: linha(s) "
                                   + ", ".join(str(x["linha"]) for x in c["vital_bloqueio"][:20]), u["id"], u["empresa_id"])
        raise HTTPException(422, problema)
    if rep:
        banco_acesso.registrar("alerta de repetição", f"{arq}: {rep}"[:500], u["id"], u["empresa_id"])
    banco_acesso.registrar("conferiu os números e o mapa", f"{arq}: {c['numeros']['clientes']} clientes, "
                           f"{c['numeros']['comunidades']} comunidades", u["id"], u["empresa_id"])
    if c["rejeicao"]["acima"]:
        banco_acesso.registrar("justificou rejeições acima do limite", f"{c['rejeicao']['rejeitadas']} de {c['rejeicao']['total']} "
                               f"linhas: {travas.limpar_justificativa(dados.justificativa)}", u["id"], u["empresa_id"])
    resposta["desligamento"] = {"tipo": tipo, "rotulo": tipos.ROTULOS[tipo], "motivo": motivo}
    return JSONResponse(_guardar(resposta, u, data, horario, idioma, tipo, motivo, cfg))


@app.post("/api/planilha/json")
async def baixar_json(arquivo: UploadFile = File(...), aba: str | None = Form(None, max_length=leitura.MAX_NOME_ABA),
                      u: dict = Depends(exigir("baixar_json"))) -> Response:
    """O JSON padronizado completo, com os números de UC: só num pedido explícito, reenviando o mesmo
    arquivo (a tradução é reprodutível) e registrado na auditoria."""
    modelo = await _ler_e_traduzir(arquivo, aba, u)
    banco_acesso.registrar("baixou o JSON da planilha (com números de UC)",
                           f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256}), {modelo.resumo.total} linhas", u["id"], u["empresa_id"])
    nome = "".join(ch for ch in sem_acento(modelo.arquivo.nome.rsplit(".", 1)[0]) if ch.isalnum() or ch in "-_")[:60] or "planilha"
    return Response(esquema_planilha.texto(modelo), media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="farol-{nome}.json"'})


class PedidoRelatorio(BaseModel):
    pacote: str = Field(max_length=pacote_.MAX_PACOTE)


@app.post("/api/planilha/relatorio")
def relatorio_planilha(dados: PedidoRelatorio, u: dict = Depends(exigir("gerar_aviso"))) -> Response:
    """Relatório da tradução (CSV): linha, situação, motivo ou correção e avisos. Sem UC nem coordenada."""
    try:
        modelo = pacote_.abrir(dados.pacote, u["id"], u["empresa_id"])
    except pacote_.PacoteRecusado as e:
        raise HTTPException(422, str(e)) from None
    banco_acesso.registrar("baixou o relatório da planilha (CSV)", f"{modelo.arquivo.nome} (sha256 {modelo.arquivo.sha256})", u["id"], u["empresa_id"])
    return Response("﻿" + travas.relatorio_csv(modelo), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="farol-relatorio-planilha.csv"'})


def _alerta_repeticao(resposta: dict, u: dict, cfg: dict) -> str | None:
    """Comunidades deste aviso que já tiveram desligamentos nos últimos D dias (com este, N ou mais): aviso amarelo, não bloqueia."""
    n, dias = cfg["repeticao_n"], cfg["repeticao_dias"]
    hoje = datetime.now(BRASILIA).date()
    anteriores = Counter()
    for a in banco_relatorios.avisos(u["empresa_id"], hoje - timedelta(days=dias), hoje):
        if a.get("status") == "cancelado":
            continue
        for m in a["municipios"]:
            for c in m["comunidades"]:
                anteriores[(m["codigo_ibge"], c["nome"], c.get("distrito"))] += 1
    repetidas = sorted({f"{c['nome'].split(' (')[0]} ({m['nome']}): {anteriores[(m['codigo_ibge'], c['nome'], c.get('distrito'))] + 1}"
                        for m in resposta["municipios"] for c in m["comunidades"]
                        if anteriores[(m["codigo_ibge"], c["nome"], c.get("distrito"))] + 1 >= n})
    if not repetidas:
        return None
    texto = f"Repetição: com este, {n} ou mais desligamentos em {dias} dias"
    resposta["conferencia"]["suspeitos"].append({"tipo": "repeticao", "texto": texto, "ucs": len(repetidas), "linhas": [],
                                                 "comunidades": repetidas})
    return f"{texto}: {', '.join(repetidas)}"


def _mensagens(municipios: list[dict], cfg: dict, data: str, horario: str, idioma: str, motivo: str, codigo: str = "") -> None:
    """A mensagem da rádio de cada município, pelo modelo da empresa (nucleo/mensagem.py), e o tempo no ar.
    Só em português (o modelo é escrito em português); nos outros idiomas fica o aviso do algoritmo."""
    for m in municipios:
        if idioma != idiomas.PADRAO:
            m["mensagem"], m["segundos_mensagem"] = None, None
            continue
        m["mensagem"] = mensagem.montar(cfg["modelo_mensagem"], mensagem.valores_do_municipio(
            m, distribuidora=cfg["nome_mensagem"], data=data, horario=horario, motivo=motivo, telefone=cfg["telefone"], codigo=codigo))
        m["segundos_mensagem"] = segundos(m["mensagem"])


def _guardar(resposta: dict, u: dict, data: str, horario: str, idioma: str, tipo: str, motivo: str, cfg: dict) -> dict:
    """Grava no histórico da empresa só o agregado (sem as linhas com problema), com a linha "gerou aviso"
    na auditoria na mesma transação, e devolve a resposta com o id, o código de verificação e quem pediu."""
    p = resposta["planilha"]
    resumo = {"linhas": p["linhas"], "validas": p["validas"], "problemas": p["total_problemas"],
              "fora_da_concessao": resposta["fora_da_concessao"]["ucs"], "prazo": resposta["prazo"],
              "corrigidas": resposta["conferencia"]["numeros"]["corrigidas"], "arquivo_sha256": resposta["conferencia"]["sha256"]}
    # do aviso de hoje, só as contagens (o texto lista imóveis e ruas e não precisa ficar guardado)
    municipios = [{**{k: m[k] for k in ("codigo_ibge", "nome", "uf", "ucs", "comunidades", "aviso", "segundos", "equipamento_vital",
                                         "mensagem", "segundos_mensagem")},
                   "hoje": {k: m["hoje"][k] for k in ("locais", "palavras", "segundos")} if m.get("hoje") else None}
                  for m in resposta["municipios"]]
    nomes = ", ".join(m["nome"] for m in municipios) or "nenhum município"
    g = banco_acesso.gravar_aviso(u["empresa_id"], u["id"], data, horario, idioma, resumo, municipios, tipo, motivo,
                                  lambda id_: f"aviso {id_}: {nomes} ({p['linhas']} linhas), {tipos.ROTULOS[tipo].lower()}")
    resposta.update(id=g["id"], codigo=g["codigo"], criado_em=g["criado_em"].isoformat(), usuario=g["solicitante"],
                    usuario_perfil=PERFIS.get(g["solicitante_perfil"], ""), status="gerado")
    if "{codigo}" in cfg["modelo_mensagem"]:   # o código só existe depois de gravado: a mensagem é refeita com ele
        _mensagens(resposta["municipios"], cfg, data, horario, idioma, motivo, g["codigo"])
        _mensagens(municipios, cfg, data, horario, idioma, motivo, g["codigo"])
        banco_acesso.atualizar_municipios(g["id"], u["empresa_id"], municipios)
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
    banco_acesso.registrar("gerou MP3 do aviso" + (" de hoje (comparativo)" if dados.comparativo else ""),
                           f"{municipio}, {segundos:.0f} s", u["id"], u["empresa_id"])
    return Response(mp3, media_type="audio/mpeg", headers={
        "Content-Disposition": f'attachment; filename="farol-aviso-{arquivo}.mp3"',
        "X-Duracao-Segundos": f"{segundos:.1f}"})


def _aviso_publico(a: dict) -> dict:
    tipo = a.get("tipo") or None
    return {"id": a["id"], "criado_em": a["criado_em"].isoformat(), "data": a["data"], "horario": a["horario"],
            "idioma": a["idioma"], "usuario": a["usuario"], "usuario_perfil": PERFIS.get(a.get("usuario_perfil"), ""),
            "resumo": a["resumo"], "municipios": a["municipios"], "status": a.get("status") or "gerado", "codigo": a.get("codigo"),
            "desligamento": {"tipo": tipo, "rotulo": tipos.ROTULOS.get(tipo, ""), "motivo": a.get("motivo")} if tipo else None}


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
    hoje = datetime.now(BRASILIA).date()
    return {**painel.resumir(avisos, hoje), "mes": painel_do_mes(u["empresa_id"], hoje)}


@app.put("/api/historico/{id_}/municipios/{codigo}/texto")
def guardar_texto_final(id_: int, codigo: str, dados: TextoFinal, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """O texto que foi para a rádio (depois da edição), gravado ao baixar o PDF ou copiar."""
    texto = dados.texto.strip()
    if not 1 <= len(texto) <= 3000:
        raise HTTPException(422, "Texto do aviso: de 1 a 3.000 caracteres.")
    a = banco_acesso.aviso(id_, u["empresa_id"])
    gerado_ = next((m.get("aviso") for m in (a or {}).get("municipios", []) if m.get("codigo_ibge") == codigo), None)
    if not banco_acesso.texto_final(id_, u["empresa_id"], codigo, texto):
        raise HTTPException(404, "Aviso ou município não encontrado nesta empresa.")
    if gerado_ is not None and texto != gerado_:
        banco_acesso.registrar("editou a mensagem", f"aviso {id_}, município {codigo}: {len(gerado_.split())} -> "
                               f"{len(texto.split())} palavras", u["id"], u["empresa_id"])
    banco_acesso.registrar("guardou o texto final", f"aviso {id_}, município {codigo}", u["id"], u["empresa_id"])
    return {"ok": True}


class Cancelamento(BaseModel):
    motivo: str = Field(max_length=1000)


class NovaData(BaseModel):
    data: str = Field(max_length=200)
    horario: str = Field(max_length=200)


def _aviso_da_empresa(id_: int, u: dict) -> dict:
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    if a.get("status") == "cancelado":
        raise HTTPException(409, "Este aviso já foi cancelado.")
    return a


@app.post("/api/historico/{id_}/cancelar")
def cancelar(id_: int, dados: Cancelamento, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Cancela o desligamento: o aviso fica no histórico, marcado, e o motivo vai para a auditoria."""
    _aviso_da_empresa(id_, u)
    motivo = tipos.limpar(dados.motivo)
    if (p := tipos.problema_outro(motivo)):
        raise HTTPException(422, f"Motivo do cancelamento: {p}")
    banco_acesso.cancelar_aviso(id_, u["empresa_id"])
    banco_acesso.registrar("cancelou o aviso", f"aviso {id_}: {motivo}", u["id"], u["empresa_id"])
    return _aviso_publico(banco_acesso.aviso(id_, u["empresa_id"]))


@app.post("/api/historico/{id_}/data")
def mudar_data(id_: int, dados: NovaData, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Muda a data ou o horário do desligamento; o antes e o depois vão para a auditoria."""
    a = _aviso_da_empresa(id_, u)
    data, horario = _texto_do_aviso("data", dados.data), _texto_do_aviso("horário", dados.horario)
    banco_acesso.mudar_data(id_, u["empresa_id"], data, horario)
    banco_acesso.registrar("mudou a data do aviso", f"aviso {id_}: de {a['data']}, {a['horario']} para {data}, {horario}",
                           u["id"], u["empresa_id"])
    return _aviso_publico(banco_acesso.aviso(id_, u["empresa_id"]))


@app.get("/api/historico/{id_}/linha-do-tempo")
def linha_do_tempo(id_: int, u: dict = Depends(exigir("ver_historico"))) -> dict:
    """Tudo o que aconteceu com o aviso, em ordem, com o nome e o perfil de quem fez (da auditoria)."""
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    envios = [e["id"] for e in banco_radios.envios(u["empresa_id"], id_)]
    linhas = banco_acesso.linhas_do_aviso(u["empresa_id"], id_, envios, (a.get("resumo") or {}).get("arquivo_sha256"))
    return {"aviso": id_, "linhas": [{"quando": r["quando"].isoformat(), "usuario": r["usuario"], "perfil": PERFIS.get(r["perfil"], ""),
                                      "acao": r["acao"], "detalhe": r["detalhe"], "codigo": auditoria.codigo_verificacao(r["hash"])}
                                     for r in linhas]}


@app.get("/api/verificar/{codigo}")
def verificar_codigo(codigo: str, u: dict = Depends(usuario_atual)) -> dict:
    """Confere um código de verificação (FRL-XXXX-XXXX-XXXX): a linha da auditoria que ele aponta, da
    própria empresa (o Admin do Farol vê de todas), e se a corrente da auditoria está íntegra."""
    h = "".join(ch for ch in codigo.upper().removeprefix("FRL") if ch.isalnum())
    if len(h) != 12 or any(ch not in "0123456789ABCDEF" for ch in h):
        raise HTTPException(422, "Código de verificação: use o formato FRL-XXXX-XXXX-XXXX.")
    ln = banco_acesso.linha_por_hash(h)
    if not ln or (u["perfil"] != "admin_farol" and ln["empresa_id"] != u["empresa_id"]):
        raise HTTPException(404, "Código não encontrado na auditoria desta empresa.")
    return {"codigo": auditoria.codigo_verificacao(ln["hash"]), "quando": ln["quando"].isoformat(), "acao": ln["acao"],
            "detalhe": ln["detalhe"], "por": ln["usuario"], "perfil": PERFIS.get(ln["perfil"], ""),
            "auditoria_integra": banco_acesso.verificar_registro()["ok"],
            "sha256_pdf": (banco_relatorios.via_por_codigo(auditoria.codigo_verificacao(ln["hash"])) or {}).get("sha256")}


# Arquivos da tela: o app, o Leaflet e as fontes embutidas no projeto (vendor/) e o logo. Nada de CDN.
app.mount("/assets/app", StaticFiles(directory=TELA), name="app")
app.mount("/assets/vendor", StaticFiles(directory=APRESENTACAO / "vendor"), name="vendor")
app.mount("/assets/marca", StaticFiles(directory=APRESENTACAO / "marca"), name="marca")
