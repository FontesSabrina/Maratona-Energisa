"""Teste do simulador de economia (Relatórios): contas, perfis, auditoria, PDF e CSV, idiomas.

Roda num esquema próprio do Postgres (apagado no fim), só com a semente de acesso (sem avisos). Confere:
- as contas puras (nucleo/simulador.py): 160.000 x 100% x 68,2% = 109.090,91 por mês (1.309.090,91 no ano);
  cenário conservador (50%) = 54.545,45; sem avisos, a medição de validação (44 s -> 14 s); com avisos, a
  média real (cancelado e município sem o aviso de hoje ficam de fora); já economizado = calculada + informada;
- perfis: os três da empresa veem; só o Admin da empresa altera; o Admin do Farol não vê; Operador e Consulta 403;
- a alteração vai para a auditoria com o antes e o depois; salvar o resto da configuração não apaga os valores;
- PDF e CSV com o código FRL e o nome de quem gerou; a tela em inglês e em espanhol.

Uso (na raiz): uv run python -W ignore testes/api/teste_simulador.py
"""

import base64
import os
import re
import sys
import zlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

os.environ.update({"FAROL_ESQUEMA": "teste_simulador", "FAROL_EMAIL": "0",
                   "FAROL_CHAVE_ARQUIVOS": base64.urlsafe_b64encode(os.urandom(32)).decode()})

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.nucleo import simulador as S  # noqa: E402
from comunidades.semente import semear  # noqa: E402

resultados = []
NOVA = "Lanterna-do-Farol-2026"
BR = timezone(timedelta(hours=-3))
FRL = re.compile(r"^FRL-[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}$")


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(q, args=()):
    with conectar() as c, c.cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


def texto_pdf(b: bytes) -> str:
    partes = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", b, re.S):
        try:
            partes.append(zlib.decompressobj().decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    return " ".join("".join(x.replace("\\(", "(").replace("\\)", ")") for x in re.findall(r"\(((?:\\.|[^\\)])*)\)", ln))
                    for ln in "\n".join(partes).splitlines())


def valor(doc, rotulo):
    return next((i["valor"] for i in doc["resumo"] if i["rotulo"] == rotulo), None)


# ---------- 1. Contas (puro) ----------
r0 = S.reducao([])
e100, e50 = S.economia(Decimal("160000"), Decimal("100"), r0["reducao"]), S.economia(Decimal("160000"), Decimal("50"), r0["reducao"])
conferir("sem avisos: medição de validação 44 s -> 14 s (68,2%)",
         r0["fonte"] == "validacao" and (r0["segundos_hoje"], r0["segundos_farol"]) == (44, 14) and S.pct(r0["reducao"] * 100) == "68,2%", str(r0))
conferir("160.000 x 100% x 68,2% = 109.090,91 por mês e 1.309.090,91 no ano",
         e100 == {"mensal": Decimal("109090.91"), "anual": Decimal("1309090.91")}, str(e100))
conferir("cenário conservador (50%): 54.545,45 por mês e 654.545,45 no ano",
         e50 == {"mensal": Decimal("54545.45"), "anual": Decimal("654545.45")}, str(e50))
_q = datetime(2026, 3, 10, 10, 0, tzinfo=BR)
_av = [
    {"id": 1, "status": "ativo", "criado_em": _q, "municipios": [
        {"codigo_ibge": "1", "hoje": {"segundos": 100}, "segundos": 30, "segundos_mensagem": 25},   # a mensagem da rádio vale
        {"codigo_ibge": "2", "hoje": None, "segundos": 10}]},                                        # sem o aviso de hoje: fora
    {"id": 2, "status": "cancelado", "criado_em": _q, "municipios": [{"codigo_ibge": "1", "hoje": {"segundos": 999}, "segundos": 1}]},
    {"id": 3, "status": "ativo", "criado_em": _q, "municipios": [{"codigo_ibge": "3", "hoje": {"segundos": 60}, "segundos": 15}]},
]
r1 = S.reducao(_av)
conferir("com avisos: média real (160 s -> 40 s = 75%), sem o cancelado nem o município sem o aviso de hoje",
         r1["fonte"] == "empresa" and (r1["segundos_hoje"], r1["segundos_farol"], r1["municipios"]) == (160, 40, 2) and r1["reducao"] == Decimal("0.75"),
         str(r1))
_en = [{"aviso_id": 1, "economia": Decimal("10.50"), "economia_tipo": "calculada"}, {"aviso_id": 1, "economia": Decimal("5"), "economia_tipo": "informada"},
       {"aviso_id": 3, "economia": None, "economia_tipo": None}]
ja = S.economizado(_en)
conferir("já economizado = calculada + informada (10,50 + 5,00 = 15,50)", ja["total"] == Decimal("15.50") and ja["envios"] == 3, str(ja))
d0 = S.documento({"gasto_min": None, "gasto_max": None, "pct_tempo": Decimal("100")}, [], [], {})
conferir("sem gasto informado: alerta, nenhum cenário inventado",
         any("não foi informado" in a for a in d0["alertas"]) and d0["secoes"][0]["linhas"] == [] and valor(d0, "Economia mensal estimada") == "—")
d1 = S.documento({"gasto_min": Decimal("160000"), "gasto_max": Decimal("300000"), "pct_tempo": Decimal("100")}, [], [], {})
conferir("faixa mín.-máx.: 4 cenários (2 faixas x 2 cenários) e o intervalo no resumo",
         len(d1["secoes"][0]["linhas"]) == 4 and valor(d1, "Economia mensal estimada") == "R$ 109.090,91 a R$ 204.545,45"
         and valor(d1, "De onde vem a redução") == "medição de validação (44 s -> 14 s)", str(d1["resumo"]))

# ---------- 2. API (banco) ----------
with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_simulador CASCADE")
senhas = {e: s for _, e, s in semear()}


def pronto(email):
    api_acesso._tentativas_ip.clear()
    c = TestClient(app, base_url="http://farol.teste")
    c.post("/api/entrar", json={"email": email, "senha": senhas[email]})
    c.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
    return c


try:
    far, adm, op, con = (pronto(e) for e in ("admin@farol.example", "admin@emg.example", "operador@emg.example", "consulta@emg.example"))
    URL, PUT = "/api/relatorios/simulador", "/api/empresa/configuracao/simulador"
    r = con.get(URL)
    j = r.json() if r.status_code == 200 else {}
    conferir("Consulta vê o simulador (sem avisos: medição de validação) e não edita",
             r.status_code == 200 and j["documento"]["reducao"]["fonte"] == "validacao" and j["pode_editar"] is False, r.text[:200])
    conferir("Admin do Farol não vê o simulador (403)", far.get(URL).status_code == 403)
    corpo = {"gasto_min": "160000", "gasto_max": "300000", "pct_tempo": "100"}
    conferir("Operador e Consulta não alteram os valores (403)", op.put(PUT, json=corpo).status_code == 403 and con.put(PUT, json=corpo).status_code == 403)
    conferir("máximo menor que o mínimo: 422 no campo gasto_max",
             (x := adm.put(PUT, json={**corpo, "gasto_max": "100"})).status_code == 422 and x.headers.get("x-farol-campo") == "gasto_max", x.text[:200])
    conferir("% fora de 0 a 100: 422", adm.put(PUT, json={**corpo, "pct_tempo": "101"}).status_code == 422)
    r = adm.put(PUT, json=corpo)
    conferir("Admin da empresa salva os valores", r.status_code == 200 and r.json()["simulador"]["gasto_min"] == "160000.00", r.text[:200])
    linha = sql("SELECT detalhe, usuario_nome, perfil FROM registro WHERE acao = 'alterou o simulador de economia' ORDER BY id DESC LIMIT 1")
    conferir("auditoria: o antes e o depois, com o nome e o perfil de quem fez",
             bool(linha) and "gasto mensal (mínimo): — → 160000.00" in linha[0][0] and "gasto mensal (máximo): — → 300000.00" in linha[0][0]
             and linha[0][1] and linha[0][2] == "admin_empresa", str(linha))
    j = op.get(URL).json()
    conferir("Operador vê: economia mensal R$ 109.090,91 a R$ 204.545,45 e anual R$ 1.309.090,91 a R$ 2.454.545,45",
             valor(j["documento"], "Economia mensal estimada") == "R$ 109.090,91 a R$ 204.545,45"
             and valor(j["documento"], "Economia anual estimada") == "R$ 1.309.090,91 a R$ 2.454.545,45"
             and valor(j["documento"], "Economia anual no cenário conservador") == "R$ 654.545,45 a R$ 1.227.272,73", str(j["documento"]["resumo"]))
    adm.put(PUT, json={**corpo, "pct_tempo": "50"})
    j = con.get(URL).json()
    conferir("com 50% salvo (cenário conservador): R$ 54.545,45 a R$ 102.272,73 por mês",
             valor(j["documento"], "Economia mensal estimada") == "R$ 54.545,45 a R$ 102.272,73", str(j["documento"]["resumo"]))
    cfg = adm.get("/api/empresa/configuracao").json()
    adm.put("/api/empresa/configuracao", json={k: cfg[k] for k in ("modelo_mensagem", "nome_mensagem", "telefone", "limite_rejeicao", "epsg_utm",
                                                                   "antecedencia_dias", "alerta_preco", "repeticao_n", "repeticao_dias", "idioma_padrao")})
    conferir("salvar o resto da configuração não apaga os valores do simulador",
             adm.get("/api/empresa/configuracao").json()["simulador"]["gasto_min"] in (160000, 160000.0, "160000.00"))
    adm.put(PUT, json=corpo)
    # PDF e CSV: código FRL e nome de quem gerou
    nome_op = sql("SELECT nome FROM usuario WHERE email = 'operador@emg.example'")[0][0]
    nome_con = sql("SELECT nome FROM usuario WHERE email = 'consulta@emg.example'")[0][0]
    p = op.get(URL.replace("simulador", "simulador.pdf"))
    cod = p.headers.get("x-codigo", "")
    txt = texto_pdf(p.content) if p.status_code == 200 else ""
    conferir("PDF: código FRL, o nome de quem gerou e a página \"Como calculamos\"",
             p.status_code == 200 and p.content[:5] == b"%PDF-" and FRL.match(cod) and cod in txt and f"Gerado por {nome_op}" in txt
             and "Como calculamos" in txt, f"{p.status_code} {cod} {[cod in txt, f'Gerado por {nome_op}' in txt, 'Como calculamos' in txt]}")
    conferir("PDF na auditoria e com a segunda via guardada",
             sql("SELECT count(*) FROM registro WHERE acao = 'gerou relatório simulador (PDF)'")[0][0] == 1
             and sql("SELECT count(*) FROM relatorio_via WHERE tipo = 'simulador' AND codigo = %s", (cod,))[0][0] == 1)
    c = con.get(URL.replace("simulador", "simulador.csv"))
    conferir("CSV (Consulta): código FRL, nome de quem gerou e os valores",
             c.status_code == 200 and re.search(r"codigo_verificacao;FRL-", c.text) and f"gerado_por;{nome_con}" in c.text and "R$ 109.090,91" in c.text,
             c.text[:300])
    # idiomas
    en = op.get(URL, headers={"X-Farol-Idioma": "en"}).json()["documento"]
    es = op.get(URL, headers={"X-Farol-Idioma": "es"}).json()["documento"]
    conferir("inglês: título e valores no formato com ponto",
             en["titulo"] == "Radio savings simulator" and valor(en, "Estimated monthly savings") == "R$ 109,090.91 to R$ 204,545.45", str(en["resumo"][:5]))
    conferir("espanhol: título e valores",
             es["titulo"] == "Simulador de ahorro con radio" and valor(es, "Ahorro mensual estimado") == "R$ 109.090,91 a R$ 204.545,45", str(es["resumo"][:5]))
    conferir("auditoria íntegra", adm.get("/api/auditoria/verificar").json()["ok"])
finally:
    with conectar() as c:
        c.execute("DROP SCHEMA IF EXISTS teste_simulador CASCADE")

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
