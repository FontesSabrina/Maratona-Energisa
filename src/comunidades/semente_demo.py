"""Semente de demonstração: um mês e meio de histórico FICTÍCIO da empresa EMG para os relatórios da apresentação.

Cria (uma vez só; rodar de novo não duplica):
- 4 rádios de demonstração (e-mails @example.com, WhatsApp fictício), com alcance por município e por comunidade;
- cerca de 16 avisos nas últimas 6 semanas, cada um a partir das UCs FICTÍCIAS a jusante de uma chave da
  rede fictícia (simulacao/planilhas_teste.py), traduzidos e calculados pelo mesmo código da API;
- envios às rádios (e-mail, WhatsApp, cópia) com valor, economia e confirmação; um envio que falhou, um
  aviso sem envio, um cancelado e um que saiu fora do prazo, para os relatórios terem o que mostrar.
Os avisos e envios recebem datas passadas (é demonstração); a auditoria registra a semente com a data
de hoje ("semente de demonstração"). Nada de cliente real: rede, clientes e rádios são fictícios.

Uso (depois de uv run python -m comunidades.semente): uv run python -m comunidades.semente_demo
"""

import sys
from datetime import datetime, timedelta
from decimal import Decimal

import geopandas as gpd

from . import config as C
from .api import app as api
from .api.comum import BRASILIA, config_empresa, segundos
from .banco import acesso as banco
from .banco import base_territorial as territorio
from .banco import radios as banco_radios
from .banco.conexao import conectar
from .nucleo import economia
from .nucleo.tipos_desligamento import TIPOS
from .simulacao import planilhas_teste

MARCA = "semente de demonstração"
TIPOS_CICLO = ["manutencao_preventiva", "poda", "obra", "troca_equipamento", "corretiva_programada", "poda", "manutencao_preventiva"]


def _codigo(nome: str) -> str | None:
    return next((c for c, n, _, _ in territorio.contornos("EPSG:4674") if n == nome), None)


def _radios(empresa_id: int, admin_id: int) -> dict[str, int]:
    existentes = {r["nome"]: r["id"] for r in banco_radios.radios(empresa_id, so_ativas=False)}
    leo, cat = _codigo("Leopoldina"), _codigo("Cataguases")
    novas = [
        {"nome": "Rádio Leopoldina FM (demonstração)", "email": "leopoldina.fm@example.com", "whatsapp": "32999990001",
         "alcance": {"municipios": [leo], "comunidades": []}, "valor_padrao": Decimal("90.00"), "cobranca": "minuto"},
        {"nome": "Rádio Comunitária Piacatuba (demonstração)", "email": "piacatuba@example.com", "whatsapp": "32999990002",
         "alcance": {"municipios": [], "comunidades": [{"municipio": leo, "nome": "Piacatuba", "distrito": "Piacatuba"},
                                                       {"municipio": leo, "nome": "Graminha", "distrito": "Piacatuba"}]},
         "valor_padrao": Decimal("150.00"), "cobranca": "fechado"},
        {"nome": "Rádio Vale do Pomba (demonstração)", "email": "valedopomba@example.com", "whatsapp": None,
         "alcance": {"municipios": [m for m in (leo, cat) if m], "comunidades": []}, "valor_padrao": Decimal("250.00"), "cobranca": "fechado"},
        {"nome": "Rádio Tebas AM (demonstração)", "email": None, "whatsapp": "32999990004",
         "alcance": {"municipios": [], "comunidades": [{"municipio": leo, "nome": "Tebas", "distrito": "Tebas"},
                                                       {"municipio": leo, "nome": "Tomé Nogueira", "distrito": "Tebas"}]},
         "valor_padrao": Decimal("70.00"), "cobranca": "minuto"},
    ]
    for r in novas:
        if r["nome"] not in existentes:
            existentes[r["nome"]] = banco_radios.criar_radio(empresa_id, admin_id, {**r, "ativa": True})
    return existentes


def _chaves(n: int) -> list[str]:
    ch = gpd.read_file(C.SINTETICO / "chaves.gpkg", ignore_geometry=True)
    escolhidas = []
    for c in ch["COD_CHAVE"].tolist():
        try:
            t = planilhas_teste.planilha(c)
        except ValueError:
            continue
        if 60 <= len(t) <= 700:
            escolhidas.append(c)
        if len(escolhidas) >= n:
            break
    return escolhidas


def _aviso(u: dict, chave: str, tipo: str, data: str, horario: str) -> dict:
    t = planilhas_teste.planilha(chave)
    conteudo = t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")
    modelo = api._traduzir(conteudo, f"demonstracao_{chave}.csv", None, u)
    cfg = config_empresa(u["empresa_id"])
    resposta = api._resultado(modelo, data, horario, "pt-BR", cfg)
    motivo = TIPOS[tipo]
    api._mensagens(resposta["municipios"], cfg, data, horario, "pt-BR", motivo)
    return api._guardar(resposta, u, data, horario, "pt-BR", tipo, motivo, cfg)


def semear_demo(n_avisos: int = 16) -> dict:
    emp = banco.empresa_por_sigla("EMG")
    if not emp:
        raise SystemExit("Rode antes: uv run python -m comunidades.semente")
    with conectar() as c:
        if c.execute("SELECT 1 FROM registro WHERE acao = %s AND empresa_id = %s", (MARCA, emp["id"])).fetchone():
            return {"criados": 0, "motivo": "a semente de demonstração já foi aplicada nesta empresa"}
    op = banco.usuario_por_email("operador@emg.example")
    adm = banco.usuario_por_email("admin@emg.example")
    radios = _radios(emp["id"], adm["id"])
    agora = datetime.now(BRASILIA).replace(second=0, microsecond=0)
    criados, envios = 0, 0
    for i, chave in enumerate(_chaves(n_avisos)):
        quem = adm if i % 5 == 4 else op
        u = {**quem, "empresa_nome": emp["nome"]}
        gerado = agora - timedelta(days=42 - i * 2.6, hours=(i * 7) % 9)
        antecedencia = 2 if i == 6 else 9          # o 7º sai em cima da hora: fora do prazo
        desl = gerado + timedelta(days=antecedencia)
        tipo = TIPOS_CICLO[i % len(TIPOS_CICLO)]
        r = _aviso(u, chave, tipo, f"{desl:%d/%m}", ["8h às 14h", "9h às 15h", "8h às 12h", "13h às 17h"][i % 4])
        with conectar() as c:
            c.execute("UPDATE aviso SET criado_em = %s WHERE id = %s", (gerado, r["id"]))
        criados += 1
        if i == 9:                                    # um sem envio registrado
            continue
        if i == 12:                                   # um cancelado (sem envio)
            banco.cancelar_aviso(r["id"], emp["id"])
            banco.registrar("cancelou o aviso", f"aviso {r['id']}: chuva forte prevista ({MARCA})", op["id"], emp["id"])
            continue
        for m in r["municipios"]:
            alvo = [radios["Rádio Leopoldina FM (demonstração)"]] if m["nome"] == "Leopoldina" else []
            if m["nome"] == "Leopoldina" and i % 3 == 0:
                alvo.append(radios["Rádio Vale do Pomba (demonstração)"])
            if m["nome"] == "Leopoldina" and any(c["distrito"] in ("Piacatuba", "Tebas") for c in m["comunidades"]) and i % 2 == 1:
                alvo.append(radios["Rádio Comunitária Piacatuba (demonstração)"])
            for k, radio_id in enumerate(alvo):
                rad = banco_radios.radio(radio_id, emp["id"])
                canal = "email" if rad["email"] and k == 0 else "whatsapp" if rad["whatsapp"] else "copia"
                texto = m.get("mensagem") or m["aviso"]
                seg, seg_hoje = segundos(texto), (m.get("hoje") or {}).get("segundos")
                antigo = Decimal("420.00") if rad["cobranca"] == "fechado" and i % 2 == 0 else None
                eco = economia.calcular(rad["cobranca"], rad["valor_padrao"], seg, seg_hoje, antigo)
                enviado = gerado + timedelta(minutes=20 + 7 * k)
                status = "falhou" if i == 3 and k == 0 else "confirmado" if canal == "email" else "enviado"
                envio_id = banco_radios.criar_envio({
                    "empresa_id": emp["id"], "aviso_id": r["id"], "municipio": m["codigo_ibge"], "municipio_nome": m["nome"],
                    "radio_id": radio_id, "radio_nome": rad["nome"], "canal": canal,
                    "destino": rad["email"] if canal == "email" else rad["whatsapp"] if canal == "whatsapp" else "", "texto": texto,
                    "valor": rad["valor_padrao"], "cobranca": rad["cobranca"], "custo": eco["custo"], "custo_antigo": antigo,
                    "economia": eco["economia"], "economia_tipo": eco["economia_tipo"], "segundos": seg, "segundos_hoje": seg_hoje,
                    "tempo_economizado": eco["tempo_economizado"], "status": status, "criado_por": quem["id"], "criado_por_nome": quem["nome"]})
                with conectar() as c:
                    c.execute("UPDATE envio SET criado_em = %s, confirmado_em = %s WHERE id = %s",
                              (enviado, enviado + timedelta(hours=2, minutes=13 * k) if status == "confirmado" else None, envio_id))
                envios += 1
    banco.registrar(MARCA, f"{criados} avisos fictícios, {envios} envios fictícios e {len(radios)} rádios de demonstração", adm["id"], emp["id"])
    return {"criados": criados, "envios": envios, "radios": len(radios)}


if __name__ == "__main__":
    print(semear_demo(int(sys.argv[1]) if len(sys.argv) > 1 else 16))
