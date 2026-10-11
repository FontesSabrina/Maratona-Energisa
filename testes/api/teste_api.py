"""Teste da API (FastAPI, em processo, com o banco local): planilha -> municípios, comunidades e aviso.

Confere:
- a base de Leopoldina no banco dá o mesmo resultado da base em arquivo (fontes/base_territorial.py);
- na CF-0066, 4 UCs ficam 1 a 55 m além da divisa, dentro de São João Nepomuceno: a API as põe lá;
- .csv (padrão do Excel brasileiro) e .xlsx dão a mesma resposta;
- uma planilha com UCs de dois municípios gera um aviso para cada um;
- cada tipo de problema aponta a linha certa, e UCs fora da concessão são contadas pela linha;
- erros de arquivo inteiro (vazio, sem coluna, grande demais) e de formulário respondem 422;
- a resposta não traz nenhum número de UC nem coordenada da planilha.

Uso (na raiz, depois do pipeline de Leopoldina e do base_concessao): uv run python testes/api/teste_api.py
"""

import io
import json
import sys

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from comunidades import distribuidora as dist_
from comunidades.api.app import app
from comunidades.banco import base_territorial as banco
from comunidades.fontes import base_territorial as BT
from comunidades.nucleo.afetados import BaseMunicipio, afetados
from comunidades.simulacao import planilhas_teste

cli = TestClient(app)
resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def enviar(conteudo: bytes, nome="planilha.csv", data="12/11", horario="8h às 14h", **extra):
    return cli.post("/api/avisos", files={"arquivo": (nome, conteudo)}, data={"data": data, "horario": horario, **extra})


def csv_bytes(t: pd.DataFrame) -> bytes:
    return t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")


def xlsx_bytes(t: pd.DataFrame) -> bytes:
    b = io.BytesIO()
    t.to_excel(b, index=False)
    return b.getvalue()


def sem_dados_da_planilha(texto: str, t: pd.DataFrame) -> list[str]:
    """UCs e coordenadas da planilha que aparecem na resposta (deve ser lista vazia)."""
    achados = [u for u in t["uc"].astype(str) if len(u) >= 6 and u in texto]
    for col in ("latitude", "longitude"):
        for v in t[col].astype(float):
            for s in (f"{v:.6f}", f"{v:.5f}", f"{v:.4f}".replace(".", ",")):
                if s in texto:
                    achados.append(s)
    return achados[:5]


# ---------- 1. Saúde e modelo ----------
r = cli.get("/api/saude")
conferir("saúde: 66 municípios da concessão no banco", r.status_code == 200 and r.json()["municipios"] == 66, r.text)
r = cli.get("/api/modelo-planilha")
conferir("modelo da planilha: CSV com o cabeçalho do modelo", r.status_code == 200
         and r.content.decode("utf-8-sig").startswith("uc;latitude;longitude;equipamento_vital;classe"), r.text[:60])
conferir("cabeçalhos de segurança (nosniff, no-store)", r.headers.get("x-content-type-options") == "nosniff"
         and r.headers.get("cache-control") == "no-store")

# ---------- 2. CF-0066: banco x arquivo, csv x xlsx ----------
t = planilhas_teste.planilha("CF-0066")
rc, rx = enviar(csv_bytes(t)), enviar(xlsx_bytes(t), "planilha.xlsx")
conferir("CF-0066 (.csv): 200", rc.status_code == 200, rc.text[:200])
j = rc.json()
m = j["municipios"][0] if j.get("municipios") else {}
conferir("CF-0066: 758 UCs, 754 em Leopoldina e 4 além da divisa em São João Nepomuceno",
         [(mm["nome"], mm["ucs"]) for mm in j["municipios"]] == [("Leopoldina", 754), ("São João Nepomuceno", 4)]
         and j["planilha"]["validas"] == 758 and j["fora_da_concessao"]["ucs"] == 0,
         json.dumps([(mm["nome"], mm["ucs"]) for mm in j["municipios"]], ensure_ascii=False))
conferir(".xlsx dá a mesma resposta que o .csv", rx.status_code == 200 and rx.json() == j)
from pyproj import Transformer
x, y = Transformer.from_crs("EPSG:4674", BT.CRS_BASE, always_xy=True).transform(t["longitude"].to_numpy(), t["latitude"].to_numpy())
# a base de Leopoldina guardada no banco x a montada dos arquivos: mesmo núcleo, mesmo resultado
cod_leo, _, _, contorno_leo = next(c for c in banco.contornos(BT.CRS_BASE) if c[1] == "Leopoldina")
do_banco = BaseMunicipio(cod_leo, "Leopoldina", "MG", contorno_leo, *banco.enderecos(cod_leo, BT.CRS_BASE))
regras = dist_.carregar().regras
rb = afetados(np.c_[x, y], [do_banco], regras, "12/11", "8h às 14h").municipios[0]
ra = afetados(np.c_[x, y], [BT.base()], regras, "12/11", "8h às 14h").municipios[0]
conferir("banco = arquivo (Leopoldina): mesmo aviso", rb.aviso == ra.aviso, f"\n  banco:   {rb.aviso}\n  arquivo: {ra.aviso}")
iguais = float((rb.ucs["COMUNIDADE_PREVISTA"].to_numpy() == ra.ucs["COMUNIDADE_PREVISTA"].to_numpy()).mean())
conferir("banco = arquivo (Leopoldina): mesma comunidade em todas as UCs", iguais == 1.0, f"{iguais:.2%}")
conferir("banco = arquivo (Leopoldina): mesmas comunidades e contagens",
         rb.comunidades.drop(columns="CONFIANCA").equals(ra.comunidades.drop(columns="CONFIANCA")))
cod_sjn, _, _, contorno_sjn = next(c for c in banco.contornos(BT.CRS_BASE) if c[1] == "São João Nepomuceno")
sjn = BaseMunicipio(cod_sjn, "São João Nepomuceno", "MG", contorno_sjn, *banco.enderecos(cod_sjn, BT.CRS_BASE))
nucleo = afetados(np.c_[x, y], [do_banco, sjn], regras, "12/11", "8h às 14h").municipios
conferir("API = núcleo com as bases do banco: os mesmos dois avisos", [mm["aviso"] for mm in j["municipios"]] == [mm.aviso for mm in nucleo],
         "\n  " + "\n  ".join(mm["aviso"] for mm in j["municipios"]))
conferir("prazo: com equipamento vital sorteado, 5 dias úteis", m["equipamento_vital"]["sim"] > 0 and "5 dias úteis" in j["prazo"]["antecedencia_minima"],
         json.dumps([m["equipamento_vital"], j["prazo"]], ensure_ascii=False))
conferir("nenhum número de UC nem coordenada na resposta (.csv)", not sem_dados_da_planilha(rc.text, t), str(sem_dados_da_planilha(rc.text, t)))
conferir("idioma en: aviso em inglês", (e := enviar(csv_bytes(t), idioma="en")).status_code == 200
         and e.json()["municipios"][0]["aviso"] != m["aviso"], e.json()["municipios"][0]["aviso"][:80] if e.status_code == 200 else e.text)

# ---------- 3. Dois municípios: CF-0066 + 40 endereços de Cataguases ----------
cod_cat = next(c for c, n, u, g in banco.contornos(BT.CRS_BASE) if n == "Cataguases")
exy, _, _ = banco.enderecos(cod_cat, BT.CRS_BASE)
lon, lat = Transformer.from_crs(BT.CRS_BASE, "EPSG:4674", always_xy=True).transform(exy[:40, 0], exy[:40, 1])
cat = pd.DataFrame({"uc": [f"9{i:09d}" for i in range(40)], "latitude": lat.round(6), "longitude": lon.round(6),
                    "equipamento_vital": "não", "classe": "residencial"})
r2 = enviar(csv_bytes(pd.concat([t, cat], ignore_index=True)))
nomes = [(mm["nome"], mm["ucs"]) for mm in r2.json().get("municipios", [])] if r2.status_code == 200 else r2.text
conferir("dois municípios: Leopoldina (754), Cataguases (40) e as 4 da divisa, um aviso cada",
         nomes == [("Leopoldina", 754), ("Cataguases", 40), ("São João Nepomuceno", 4)], str(nomes))
if r2.status_code == 200 and len(r2.json()["municipios"]) == 2:
    conferir("o aviso de Cataguases cita Cataguases", "em Cataguases" in r2.json()["municipios"][1]["aviso"], r2.json()["municipios"][1]["aviso"])

# ---------- 4. Problemas por linha ----------
ruins = pd.DataFrame([
    {"uc": "", "latitude": "-21,53", "longitude": "-42,64"},              # linha 2: sem UC
    {"uc": "1000000001", "latitude": "", "longitude": "-42,64"},          # 3: sem coordenada
    {"uc": "1000000002", "latitude": "-42,64", "longitude": "-21,53"},    # 4: trocadas
    {"uc": "1000000003", "latitude": "40,0", "longitude": "-3,7"},        # 5: fora do Brasil
    {"uc": "1000000004", "latitude": "-21,5321", "longitude": "-42,6412"},  # 6: válida
    {"uc": "1000000004", "latitude": "-21,5322", "longitude": "-42,6413"},  # 7: repetida
    {"uc": "1000000005", "latitude": "-23,55", "longitude": "-46,63", "equipamento_vital": "talvez"},  # 8: São Paulo + vital inválido
])
r3 = enviar(ruins.to_csv(sep=";", index=False).encode("utf-8"))
j3 = r3.json() if r3.status_code == 200 else {}
probs = {p["linha"]: p["motivo"] for p in j3.get("planilha", {}).get("problemas", [])}
esperado = {2: "sem número de UC", 3: "sem coordenada", 4: "trocadas", 5: "fora do Brasil", 7: "repetida (já aparece na linha 6)", 8: "a confirmar"}
conferir("cada problema aponta a linha certa", r3.status_code == 200 and all(k in probs and v in probs[k] for k, v in esperado.items()),
         json.dumps(probs, ensure_ascii=False))
conferir("UC em São Paulo: fora da concessão, pela linha (8)", j3.get("fora_da_concessao") == {"ucs": 1, "linhas": [8]},
         json.dumps(j3.get("fora_da_concessao"), ensure_ascii=False))
conferir("a válida (linha 6) entra em Leopoldina", [mm["nome"] for mm in j3.get("municipios", [])] == ["Leopoldina"])

# ---------- 5. Erros da planilha inteira e do formulário ----------
casos = {
    "arquivo vazio": enviar(b""),
    "sem a coluna longitude": enviar("uc;latitude\n1;-21,5\n".encode()),
    "mais de 10 MB": enviar(b"uc;latitude;longitude\n" + b"1;-21,5;-42,6\n" * 800_000),
    "xlsx corrompido": enviar(b"PK\x03\x04lixo", "x.xlsx"),
    "idioma inexistente": enviar(csv_bytes(t), idioma="fr"),
    "data longa demais": enviar(csv_bytes(t), data="x" * 41),
}
for nome, rr in casos.items():
    conferir(f"erro tratado ({nome}): 422 com mensagem", rr.status_code == 422 and "detail" in rr.json(), f"{rr.status_code} {rr.text[:120]}")

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
print("\nAviso da CF-0066 pela API:\n " + m.get("aviso", ""))
sys.exit(1 if falhas else 0)
