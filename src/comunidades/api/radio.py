"""Rádios, configuração da empresa, PDF do roteiro e envio do aviso (e-mail, WhatsApp, cópia), com confirmação.

- Configuração da empresa (modelo da mensagem, nome falado, telefone, limite de rejeição, fuso UTM,
  antecedência): só o Admin da empresa.
- Rádios: o Admin da empresa cadastra e altera; o Operador só acrescenta ("+ Nova rádio" no envio).
- Envio: quem gera aviso escolhe a rádio, informa o valor (gravado no envio) e manda. Por e-mail, o
  servidor gera o PDF e o MP3, guarda os dois cifrados (cofre.py), manda pelo SMTP configurado e põe
  no e-mail o link "Confirmar recebimento" (token de uso único, 7 dias, só o hash no banco).
- Confirmação: página pública, sem login. Abrir o link só mostra a página; confirmar é um POST (um
  leitor de e-mail que abre o link sozinho não confirma nada).
Tudo o que alguém faz vai para a auditoria com o nome de quem fez (do login).
"""

import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from .. import cofre, correio
from ..apresentacao import audio, confirmacao, email_radio, pdf_radio
from ..banco import acesso as banco_acesso
from ..banco import base_territorial as banco_territorio
from ..banco import radios as banco
from ..config import sem_acento
from ..nucleo import economia, mensagem
from ..nucleo import radios as alcance_
from ..nucleo.acesso import PERFIS, problema_email
from ..nucleo.tipos_desligamento import limpar
from ..segredos import segredo
from .acesso import exigir
from .comum import AUDIO, AVISO_FICTICIO, BRASILIA, config_empresa, segundos

rotas = APIRouter()
LIMITE_EMAILS, JANELA_EMAILS = 30, 3600          # e-mails para rádios por usuário por hora
_emails: dict[int, deque] = defaultdict(deque)
_NUMEROS = re.compile(r"\d[\d.\-/ ]{4,}\d")
CSP_PAGINA = ("default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'; "
              "frame-ancestors 'none'; object-src 'none'")


def _municipios_concessao() -> set[str]:
    return {c for c, _, _, _ in banco_territorio.contornos("EPSG:4674")}


def _dinheiro(d: Decimal | None) -> str | None:
    return None if d is None else f"{Decimal(d):.2f}"


# ---------- Configuração da empresa ----------
class Configuracao(BaseModel):
    modelo_mensagem: str = Field(max_length=mensagem.MAX_MODELO)
    nome_mensagem: str = Field(max_length=120)
    telefone: str = Field("", max_length=40)
    limite_rejeicao: float = Field(ge=0, le=0.5)
    epsg_utm: int = Field(ge=31960, le=31985)
    antecedencia_dias: int = Field(ge=1, le=90)


@rotas.get("/api/empresa/configuracao")
def ver_configuracao(u: dict = Depends(exigir("configurar_empresa"))) -> dict:
    return {**config_empresa(u["empresa_id"]), "campos": list(mensagem.CAMPOS), "modelo_padrao": mensagem.PADRAO}


@rotas.put("/api/empresa/configuracao")
def salvar_configuracao(dados: Configuracao, u: dict = Depends(exigir("configurar_empresa"))) -> dict:
    if (p := mensagem.problema_modelo(dados.modelo_mensagem)):
        raise HTTPException(422, p)
    nome = limpar(dados.nome_mensagem)
    if len(nome) < 2:
        raise HTTPException(422, "Nome da empresa na mensagem: de 2 a 120 caracteres.")
    antes = config_empresa(u["empresa_id"])
    novo = {"modelo_mensagem": dados.modelo_mensagem.strip(), "nome_mensagem": nome, "telefone": limpar(dados.telefone),
            "limite_rejeicao": round(dados.limite_rejeicao, 4), "epsg_utm": dados.epsg_utm, "antecedencia_dias": dados.antecedencia_dias}
    banco.salvar_config(u["empresa_id"], u["id"], novo)
    mudou = [k for k in novo if str(novo[k]) != str(antes.get(k))]
    banco_acesso.registrar("alterou a configuração da empresa", ", ".join(mudou) or "nada mudou", u["id"], u["empresa_id"])
    return ver_configuracao(u)


# ---------- Rádios ----------
class DadosRadio(BaseModel):
    nome: str = Field(max_length=200)
    email: str | None = Field(None, max_length=254)
    whatsapp: str | None = Field(None, max_length=40)
    alcance: dict = Field(default_factory=dict)
    valor_padrao: str | float | None = None
    cobranca: Literal["fechado", "minuto"] = "fechado"
    ativa: bool = True


def _radio_publica(r: dict) -> dict:
    return {"id": r["id"], "nome": r["nome"], "email": r["email"], "whatsapp": r["whatsapp"], "alcance": r["alcance"],
            "valor_padrao": _dinheiro(r["valor_padrao"]), "cobranca": r["cobranca"], "ativa": r["ativa"],
            "valor_sugerido": _dinheiro(r["ultimo_valor"] if r["ultimo_valor"] is not None else r["valor_padrao"]),
            "cobranca_sugerida": r["ultima_cobranca"] or r["cobranca"]}


def _validar_radio(d: DadosRadio) -> dict:
    nome = limpar(d.nome)
    if not 2 <= len(nome) <= 80:
        raise HTTPException(422, "Nome da rádio: de 2 a 80 caracteres.")
    email = (d.email or "").strip().lower() or None
    if email and (p := problema_email(email)):
        raise HTTPException(422, f"E-mail da rádio: {p}")
    whats = re.sub(r"\D", "", d.whatsapp or "") or None
    if whats and not 10 <= len(whats) <= 13:
        raise HTTPException(422, "WhatsApp da rádio: de 10 a 13 algarismos, com o DDD (e o 55 do Brasil, se quiser).")
    if not email and not whats:
        raise HTTPException(422, "Informe o e-mail ou o WhatsApp da rádio.")
    try:
        valor = economia.reais(d.valor_padrao)
        alcance = alcance_.normalizar_alcance(d.alcance, _municipios_concessao())
    except ValueError as e:
        raise HTTPException(422, f"Rádio: {e}.") from None
    return {"nome": nome, "email": email, "whatsapp": whats, "alcance": alcance, "valor_padrao": valor, "cobranca": d.cobranca,
            "ativa": d.ativa}


@rotas.get("/api/radios")
def listar_radios(u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    return {"radios": [_radio_publica(r) for r in banco.radios(u["empresa_id"], so_ativas=u["perfil"] != "admin_empresa")]}


@rotas.post("/api/radios")
def criar_radio(dados: DadosRadio, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Cadastra uma rádio da empresa (o Operador usa no envio: "+ Nova rádio")."""
    d = _validar_radio(dados)
    d["ativa"] = True
    id_ = banco.criar_radio(u["empresa_id"], u["id"], d)
    banco_acesso.registrar("cadastrou rádio", f"{d['nome']} ({len(d['alcance']['municipios'])} município(s), "
                           f"{len(d['alcance']['comunidades'])} comunidade(s))", u["id"], u["empresa_id"])
    return {"radio": _radio_publica(banco.radio(id_, u["empresa_id"]))}


@rotas.patch("/api/radios/{id_}")
def alterar_radio(id_: int, dados: DadosRadio, u: dict = Depends(exigir("gerenciar_radios"))) -> dict:
    antes = banco.radio(id_, u["empresa_id"])
    if not antes:
        raise HTTPException(404, "Rádio não encontrada nesta empresa.")
    d = _validar_radio(dados)
    banco.alterar_radio(id_, u["empresa_id"], d)
    mudou = [k for k in ("nome", "email", "whatsapp", "alcance", "valor_padrao", "cobranca", "ativa") if str(d[k]) != str(antes[k])]
    banco_acesso.registrar("alterou cadastro de rádio", f"{d['nome']}: {', '.join(mudou) or 'nada mudou'}", u["id"], u["empresa_id"])
    return {"radio": _radio_publica(banco.radio(id_, u["empresa_id"]))}


# ---------- Aviso: rádios sugeridas, PDF e envios ----------
def _aviso(id_: int, u: dict, ativo: bool = False) -> dict:
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    if ativo and a.get("status") == "cancelado":
        raise HTTPException(409, "Este desligamento foi cancelado: nada é enviado.")
    return a


def _municipio(a: dict, codigo: str) -> dict:
    m = next((m for m in a["municipios"] if m.get("codigo_ibge") == codigo), None)
    if not m:
        raise HTTPException(404, "Município não encontrado neste aviso.")
    return m


@rotas.get("/api/historico/{id_}/radios")
def sugerir_radios(id_: int, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Para cada município do aviso: as rádios que alcançam as comunidades afetadas e as comunidades sem rádio."""
    a = _aviso(id_, u)
    radios = banco.radios(u["empresa_id"])
    return {"radios": [_radio_publica(r) for r in radios],
            "municipios": [{"codigo_ibge": m["codigo_ibge"], "nome": m["nome"], **alcance_.cobertura(radios, m)} for m in a["municipios"]]}


def _texto_seguro(texto: str, cfg: dict, a: dict) -> str:
    """O texto que vai para a rádio: de 1 a 3.000 caracteres, sem número longo (UC, CPF), e-mail nem site.
    O telefone de atendimento e o código do aviso são permitidos."""
    t = " ".join(str(texto).replace("\r", "").split())
    if not 1 <= len(t) <= mensagem.MAX_MENSAGEM:
        raise HTTPException(422, "Texto do aviso: de 1 a 3.000 caracteres.")
    resto = t
    for permitido in (cfg["telefone"], a.get("codigo") or ""):
        if permitido:
            resto = resto.replace(permitido, " ")
    if _NUMEROS.search(resto) or "@" in resto or re.search(r"https?://|www\.", resto, re.I):
        raise HTTPException(422, "O texto não pode ter números longos (UC, CPF, telefone de cliente), e-mail nem site.")
    return t


def _gerar_pdf(a: dict, m: dict, texto: str, u: dict, cfg: dict) -> tuple[str, bytes]:
    situacao = lambda c: "vizinha" if c.get("fragmento") else "parte" if c.get("parcial") else "inteira"
    nome = lambda c: f"{alcance_.nome_base(c['nome'])} ({'Sede' if c.get('distrito') == m['nome'] else c.get('distrito')})"
    grupos = {s: [nome(c) for c in m["comunidades"] if situacao(c) == s] for s in ("inteira", "parte", "vizinha")}
    q = a["criado_em"].astimezone(BRASILIA)
    solicitado = (f"Solicitado por {a['usuario']} ({PERFIS.get(a.get('usuario_perfil'), '')}) em {q:%d/%m/%Y} às {q:%H:%M}"
                  f" · código de verificação {a.get('codigo') or '-'}")
    pdf = pdf_radio.roteiro(municipio=m["nome"], uf=m["uf"], empresa=cfg["nome_mensagem"], data=a["data"], horario=a["horario"],
                            tipo=a.get("motivo") or "", texto=texto, inteiras=grupos["inteira"], parciais=grupos["parte"],
                            vizinhas=grupos["vizinha"], prazo=f"{a['resumo']['prazo']['antecedencia_minima']} ({a['resumo']['prazo']['norma']})",
                            vital_sim=m["equipamento_vital"]["sim"], vital_a_confirmar=m["equipamento_vital"]["a_confirmar"],
                            solicitado=solicitado, aviso_id=a["id"], aviso_ficticio=AVISO_FICTICIO, gerado_por=u["nome"],
                            gerado_em=datetime.now(BRASILIA))
    base = "-".join(sem_acento(m["nome"]).lower().split()) or "municipio"
    return f"farol-aviso-{base}-{a['data'].replace('/', '-')}.pdf", pdf


class PedidoPdf(BaseModel):
    texto: str = Field(max_length=mensagem.MAX_MENSAGEM + 500)


@rotas.post("/api/historico/{id_}/municipios/{codigo}/pdf")
def baixar_pdf(id_: int, codigo: str, dados: PedidoPdf, u: dict = Depends(exigir("gerar_aviso"))) -> Response:
    """O PDF do roteiro para a rádio, gerado no servidor com o texto (editado) do município; fica na auditoria."""
    a = _aviso(id_, u)
    m, cfg = _municipio(a, codigo), config_empresa(u["empresa_id"])
    nome, pdf = _gerar_pdf(a, m, _texto_seguro(dados.texto, cfg, a), u, cfg)
    banco_acesso.registrar("gerou PDF", f"aviso {id_}, município {codigo}", u["id"], u["empresa_id"])
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nome}"'})


class PedidoEnvio(BaseModel):
    municipio: str = Field(pattern=r"^\d{7}$")
    radio_id: int
    canal: Literal["email", "whatsapp", "copia"]
    texto: str = Field(max_length=mensagem.MAX_MENSAGEM + 500)
    valor: str | float = Field(...)
    cobranca: Literal["fechado", "minuto"]
    custo_antigo: str | float | None = None


def _envio_publico(e: dict) -> dict:
    return {"id": e["id"], "aviso_id": e["aviso_id"], "municipio": e["municipio"], "municipio_nome": e["municipio_nome"],
            "radio_id": e["radio_id"], "radio_nome": e["radio_nome"], "canal": e["canal"], "destino": e["destino"],
            "status": e["status"], "valor": _dinheiro(e["valor"]), "cobranca": e["cobranca"], "custo": _dinheiro(e["custo"]),
            "custo_antigo": _dinheiro(e["custo_antigo"]), "economia": _dinheiro(e["economia"]), "economia_tipo": e["economia_tipo"],
            "segundos": e["segundos"], "segundos_hoje": e["segundos_hoje"], "tempo_economizado": e["tempo_economizado"],
            "por": e["criado_por_nome"], "criado_em": e["criado_em"].isoformat(),
            "confirmado_em": e["confirmado_em"].isoformat() if e["confirmado_em"] else None, "arquivos": list(e["arquivos"] or [])}


def _limite_emails(usuario_id: int) -> None:
    agora, fila = time.monotonic(), _emails[usuario_id]
    while fila and agora - fila[0] > JANELA_EMAILS:
        fila.popleft()
    if len(fila) >= LIMITE_EMAILS:
        raise HTTPException(429, f"Limite de {LIMITE_EMAILS} e-mails para rádios por hora atingido. Tente mais tarde.")
    fila.append(agora)


def url_publica() -> str:
    """O endereço público do Farol para o link do e-mail (FAROL_URL_PUBLICA); nunca o Host do pedido."""
    return (segredo("FAROL_URL_PUBLICA") or "http://127.0.0.1:8000").rstrip("/")


@rotas.post("/api/historico/{id_}/envios")
def enviar(id_: int, dados: PedidoEnvio, u: dict = Depends(exigir("gerar_aviso"))) -> dict:
    """Envia o aviso de um município para uma rádio (e-mail, WhatsApp ou cópia), com o valor gravado no envio."""
    a = _aviso(id_, u, ativo=True)
    m, cfg = _municipio(a, dados.municipio), config_empresa(u["empresa_id"])
    r = banco.radio(dados.radio_id, u["empresa_id"])
    if not r or not r["ativa"]:
        raise HTTPException(404, "Rádio não encontrada nesta empresa.")
    destino = r["email"] if dados.canal == "email" else r["whatsapp"] if dados.canal == "whatsapp" else ""
    if dados.canal != "copia" and not destino:
        raise HTTPException(422, f"Esta rádio não tem {'e-mail' if dados.canal == 'email' else 'WhatsApp'} cadastrado.")
    texto = _texto_seguro(dados.texto, cfg, a)
    try:
        valor, custo_antigo = economia.reais(dados.valor), economia.reais(dados.custo_antigo)
    except ValueError as e:
        raise HTTPException(422, f"Valor: {e}.") from None
    if valor is None:
        raise HTTPException(422, "Informe o valor do envio (R$).")
    if dados.canal == "email":
        if not correio.ligado():
            raise HTTPException(503, "O envio por e-mail está desligado neste servidor. Use o WhatsApp ou copie a mensagem.")
        if not cofre.disponivel():
            raise HTTPException(503, "Sem a chave do cofre (FAROL_CHAVE_ARQUIVOS): o PDF e o MP3 enviados não seriam guardados.")
        _limite_emails(u["id"])
    seg, seg_hoje = segundos(texto), (m.get("hoje") or {}).get("segundos")
    eco = economia.calcular(dados.cobranca, valor, seg, seg_hoje, custo_antigo)
    envio_id = banco.criar_envio({
        "empresa_id": u["empresa_id"], "aviso_id": a["id"], "municipio": m["codigo_ibge"], "municipio_nome": m["nome"],
        "radio_id": r["id"], "radio_nome": r["nome"], "canal": dados.canal, "destino": destino or "", "texto": texto,
        "valor": valor, "cobranca": dados.cobranca, "custo": eco["custo"], "custo_antigo": custo_antigo, "economia": eco["economia"],
        "economia_tipo": eco["economia_tipo"], "segundos": seg, "segundos_hoje": seg_hoje, "tempo_economizado": eco["tempo_economizado"],
        "status": "preparando" if dados.canal == "email" else "enviado", "criado_por": u["id"], "criado_por_nome": u["nome"]})
    banco_acesso.registrar("informou o valor do envio", f"envio {envio_id} ({r['nome']}): R$ {valor:.2f}, "
                           f"{economia.COBRANCAS[dados.cobranca]}" + (f", custo antigo informado R$ {custo_antigo:.2f}" if custo_antigo is not None else "")
                           + (f", economia {eco['economia_tipo']} R$ {eco['economia']:.2f}" if eco["economia"] is not None else ""),
                           u["id"], u["empresa_id"])
    if m.get("texto_final") != texto:
        banco_acesso.texto_final(a["id"], u["empresa_id"], m["codigo_ibge"], texto)
    resposta = {}
    if dados.canal == "email":
        resposta = _por_email(a, m, r, texto, envio_id, u, cfg)
    elif dados.canal == "whatsapp":
        numero = destino if len(destino) > 11 else "55" + destino
        resposta["whatsapp_url"] = f"https://wa.me/{numero}?text={quote(texto)}"
        banco_acesso.registrar("enviou por WhatsApp", f"envio {envio_id}: aviso {a['id']}, {m['nome']} para {r['nome']}", u["id"], u["empresa_id"])
    else:
        banco_acesso.registrar("copiou a mensagem para a rádio", f"envio {envio_id}: aviso {a['id']}, {m['nome']} para {r['nome']}",
                               u["id"], u["empresa_id"])
    return {"envio": _envio_publico(banco.envio(envio_id, u["empresa_id"])), **resposta}


def _por_email(a: dict, m: dict, r: dict, texto: str, envio_id: int, u: dict, cfg: dict) -> dict:
    nome_pdf, pdf = _gerar_pdf(a, m, texto, u, cfg)
    mp3 = None
    if AUDIO and a.get("idioma", "pt-BR") == "pt-BR":
        try:
            dados_mp3, _ = audio.mp3(texto, "pt-BR")
            mp3 = (nome_pdf.replace(".pdf", ".mp3"), dados_mp3)
        except Exception:  # noqa: BLE001 (sem o MP3, o e-mail vai com o PDF e diz isso)
            mp3 = None
    for tipo, (nome, dados) in (("pdf", (nome_pdf, pdf)), ("mp3", mp3)) if mp3 else (("pdf", (nome_pdf, pdf)),):
        banco.guardar_arquivo(envio_id, u["empresa_id"], tipo, nome, len(dados), cofre.cifrar(dados, u["empresa_id"], envio_id, tipo))
    token = secrets.token_urlsafe(32)
    banco.definir_token(envio_id, token)
    msg = email_radio.mensagem(remetente=correio.remetente(), destino=r["email"], municipio=m["nome"], uf=m["uf"], data=a["data"],
                               horario=a["horario"], empresa=cfg["nome_mensagem"], texto=texto, codigo=a.get("codigo") or "",
                               link_confirmar=f"{url_publica()}/confirmar/{token}", pdf=(nome_pdf, pdf), mp3=mp3,
                               aviso_ficticio=AVISO_FICTICIO)
    banco.mudar_status(envio_id, "enviado")
    banco_acesso.registrar("enviou por e-mail", f"envio {envio_id}: aviso {a['id']}, {m['nome']} para {r['nome']} ({r['email']})"
                           f", PDF{' e MP3' if mp3 else ''}", u["id"], u["empresa_id"])
    try:
        correio.enviar(msg)
    except correio.FalhaEnvio as e:
        banco.mudar_status(envio_id, "falhou")
        banco_acesso.registrar("envio por e-mail falhou", f"envio {envio_id}: {e}", u["id"], u["empresa_id"])
        return {"erro": f"O e-mail não foi entregue: {e}."}
    banco.mudar_status(envio_id, "entregue")
    banco_acesso.registrar("e-mail entregue ao servidor de e-mail", f"envio {envio_id} para {r['nome']}", u["id"], u["empresa_id"])
    return {}


@rotas.get("/api/historico/{id_}/envios")
def envios_do_aviso(id_: int, u: dict = Depends(exigir("ver_historico"))) -> dict:
    _aviso(id_, u)
    return {"envios": [_envio_publico(e) for e in banco.envios(u["empresa_id"], id_)]}


@rotas.get("/api/envios/{id_}/arquivos/{tipo}")
def baixar_arquivo(id_: int, tipo: Literal["pdf", "mp3"], u: dict = Depends(exigir("ver_historico"))) -> Response:
    """O PDF ou o MP3 que foi para a rádio, decifrado na hora (fica na auditoria)."""
    e = banco.envio(id_, u["empresa_id"])
    arq = banco.arquivo(id_, u["empresa_id"], tipo) if e else None
    if not arq:
        raise HTTPException(404, "Arquivo não encontrado nesta empresa.")
    try:
        dados = cofre.decifrar(arq["cifrado"], u["empresa_id"], id_, tipo)
    except cofre.SemChave:
        raise HTTPException(503, "Sem a chave do cofre neste servidor.") from None
    except cofre.Violado:
        banco_acesso.registrar("arquivo enviado não confere (cofre)", f"envio {id_}, {tipo}", u["id"], u["empresa_id"])
        raise HTTPException(409, "O arquivo guardado não confere (alterado). Nada foi entregue.") from None
    banco_acesso.registrar(f"baixou o {tipo.upper()} enviado", f"envio {id_} ({e['radio_nome']})", u["id"], u["empresa_id"])
    return Response(dados, media_type="application/pdf" if tipo == "pdf" else "audio/mpeg",
                    headers={"Content-Disposition": f'attachment; filename="{arq["nome"]}"'})


# ---------- Confirmação pela rádio (pública, sem login) ----------
def _pagina(html: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(html, status_code=status, headers={"Content-Security-Policy": CSP_PAGINA, "Cache-Control": "no-store"})


def _token_valido(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{40,60}", token or ""))


@rotas.get("/confirmar/{token}", include_in_schema=False)
def pagina_confirmar(token: str) -> HTMLResponse:
    """Só mostra (não confirma): o link pode ser aberto por um leitor de e-mail automático."""
    e = banco.envio_pelo_token(token) if _token_valido(token) else None
    if not e:
        return _pagina(confirmacao.pagina("Link inválido", "Este link de confirmação não existe."), 404)
    if e["confirmado_em"]:
        return _pagina(confirmacao.pagina("Recebimento já confirmado", f"O recebimento do aviso de {e['municipio_nome']} já foi confirmado. Obrigado."))
    if e["token_expira"] < datetime.now(e["token_expira"].tzinfo):
        return _pagina(confirmacao.pagina("Link vencido", "Este link venceu (vale 7 dias). Fale com a distribuidora."), 410)
    return _pagina(confirmacao.pagina("Confirmar o recebimento",
                                      f"{e['radio_nome']}: aviso de desligamento programado de {e['municipio_nome']}, dia {e['data']}, das {e['horario']}.",
                                      acao=f"/confirmar/{token}"))


@rotas.post("/confirmar/{token}", include_in_schema=False)
def confirmar(token: str, request: Request) -> HTMLResponse:
    origem = request.headers.get("origin")
    if origem and origem != "null" and urlsplit(origem).netloc != request.headers.get("host", ""):
        return _pagina(confirmacao.pagina("Não confirmado", "Pedido de outra origem."), 403)
    e = banco.confirmar(token) if _token_valido(token) else None
    if not e:
        return _pagina(confirmacao.pagina("Não confirmado", "O link não vale mais (já usado, vencido ou inexistente)."), 410)
    banco_acesso.registrar("rádio confirmou o recebimento", f"envio {e['id']}: {e['radio_nome']}, aviso {e['aviso_id']} ({e['municipio_nome']})",
                           None, e["empresa_id"])
    return _pagina(confirmacao.pagina("Recebimento confirmado", f"Obrigado, {e['radio_nome']}. A distribuidora já sabe que o aviso chegou."))
