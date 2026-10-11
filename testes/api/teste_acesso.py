"""Teste do login, das sessões e das permissões (FastAPI em processo, Postgres local).

Roda num esquema próprio (FAROL_ESQUEMA=teste_acesso), criado do zero e apagado no fim: os usuários
de verdade não são tocados. Confere:
- sem login, tudo responde 401 (menos /api/saude); senha errada e e-mail desconhecido dão a mesma mensagem;
- a senha temporária só serve para trocar a senha; a senha nova segue a regra;
- a matriz de permissões de cada perfil (gerar aviso, histórico, usuários, empresas, registro);
- o histórico guarda só o agregado (nenhuma UC nem coordenada) e é isolado por empresa;
- 5 senhas erradas bloqueiam; sair e sessão vencida encerram; outra origem é recusada;
- último admin protegido; usuário bloqueado perde a sessão; a semente não duplica nada;
- no banco, só o hash Argon2id da senha e o hash do token da sessão.

Uso (na raiz): uv run python -W ignore testes/api/teste_acesso.py
"""

import os
import sys

os.environ["FAROL_ESQUEMA"] = "teste_acesso"

from fastapi.testclient import TestClient  # noqa: E402

from comunidades.api import acesso as api_acesso  # noqa: E402
from comunidades.api.app import app  # noqa: E402
from comunidades.banco.conexao import conectar  # noqa: E402
from comunidades.semente import semear  # noqa: E402
from comunidades.simulacao import planilhas_teste  # noqa: E402

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def sql(q, args=()):
    with conectar() as c, c.cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


with conectar() as c:
    c.execute("DROP SCHEMA IF EXISTS teste_acesso CASCADE")
senhas = {email: s for _, email, s in semear()}
conferir("semente: 4 usuários criados, um de cada perfil", len(senhas) == 4, str(list(senhas)))
NOVA = "Lanterna-do-Farol-2026"
planilha = planilhas_teste.planilha("CF-0066").to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")


def cliente() -> TestClient:
    api_acesso._tentativas_ip.clear()
    return TestClient(app, base_url="http://farol.teste")


def entrar(email, senha, c=None):
    c = c or cliente()
    return c, c.post("/api/entrar", json={"email": email, "senha": senha})


def pronto(email):
    """Entra com a temporária e troca a senha; devolve o cliente com a sessão."""
    c, r = entrar(email, senhas[email])
    c.post("/api/senha", json={"atual": senhas[email], "nova": NOVA})
    return c


def gerar(c):
    return c.post("/api/avisos", files={"arquivo": ("p.csv", planilha)}, data={"data": "12/11", "horario": "8h às 14h"})


# ---------- 1. Sem login ----------
anon = cliente()
conferir("sem login: /api/saude responde", anon.get("/api/saude").status_code == 200)
fechadas = {"GET /api/config": anon.get("/api/config"), "GET /api/concessao": anon.get("/api/concessao"),
            "GET /api/historico": anon.get("/api/historico"), "GET /api/painel": anon.get("/api/painel"), "GET /api/usuarios": anon.get("/api/usuarios"),
            "POST /api/avisos": gerar(anon), "GET /api/modelo-planilha": anon.get("/api/modelo-planilha")}
conferir("sem login: todas as outras rotas respondem 401", all(r.status_code == 401 for r in fechadas.values()),
         str({k: r.status_code for k, r in fechadas.items()}))

# ---------- 2. Login ----------
_, errada = entrar("operador@emg.example", "senha-errada-123")
_, desconhecido = entrar("ninguem@emg.example", "senha-errada-123")
conferir("senha errada e e-mail desconhecido: mesma resposta (401, mesma mensagem)",
         errada.status_code == desconhecido.status_code == 401 and errada.json() == desconhecido.json(), f"{errada.text} | {desconhecido.text}")
op, r = entrar("operador@emg.example", senhas["operador@emg.example"])
cookie = r.headers.get("set-cookie", "")
conferir("login com a temporária: 200 e cookie HttpOnly, SameSite=Strict", r.status_code == 200 and "httponly" in cookie.lower()
         and "samesite=strict" in cookie.lower(), cookie[:120])
conferir("com a temporária: /api/eu pede troca de senha e o resto é barrado (403)",
         op.get("/api/eu").json()["usuario"]["trocar_senha"] is True and op.get("/api/config").status_code == 403)
fracas = {s: op.post("/api/senha", json={"atual": senhas["operador@emg.example"], "nova": s}).status_code
          for s in ("curta-1", "aaaaaaaaaaaaaaa", "meu-operador-2026", senhas["operador@emg.example"])}
conferir("senha nova fraca (curta, repetida, com o e-mail, igual à atual) é recusada", all(v == 422 for v in fracas.values()), str(fracas))
conferir("senha atual errada não troca", op.post("/api/senha", json={"atual": "errada", "nova": NOVA}).status_code == 422)
r = op.post("/api/senha", json={"atual": senhas["operador@emg.example"], "nova": NOVA})
conferir("troca de senha válida libera a tela", r.status_code == 200 and op.get("/api/config").status_code == 200, r.text[:120])

# ---------- 3. Matriz de permissões ----------
clientes = {"operador": op, "admin_empresa": pronto("admin@emg.example"), "consulta": pronto("consulta@emg.example"),
            "admin_farol": pronto("admin@farol.example")}
esperado = {  # rota -> perfis que podem
    "gerar aviso": {"admin_empresa", "operador"}, "histórico": {"admin_empresa", "operador", "consulta"},
    "dashboard": {"admin_empresa", "operador", "consulta"},
    "usuários": {"admin_empresa"}, "empresas": {"admin_farol"}, "registro": {"admin_farol", "admin_empresa"},
}
rotas = {"gerar aviso": gerar, "histórico": lambda c: c.get("/api/historico"), "dashboard": lambda c: c.get("/api/painel"), "usuários": lambda c: c.get("/api/usuarios"),
         "empresas": lambda c: c.get("/api/empresas"), "registro": lambda c: c.get("/api/registro")}
erros = []
for rota, f in rotas.items():
    for perfil, c in clientes.items():
        st = f(c).status_code
        if (st == 200) != (perfil in esperado[rota]) or st not in (200, 403):
            erros.append(f"{perfil} {rota}: {st}")
conferir("matriz de permissões: cada perfil acessa só o que pode (o resto 403)", not erros, "; ".join(erros))

# ---------- 4. Histórico ----------
g = gerar(op).json()
hist = clientes["consulta"].get("/api/historico").json()["avisos"]
conferir("aviso gerado entra no histórico da empresa, visível para Consulta", any(a["id"] == g["id"] for a in hist), str([a["id"] for a in hist]))
texto_hist = clientes["consulta"].get(f"/api/historico/{g['id']}").text
ucs = planilhas_teste.planilha("CF-0066")
vazou = [u for u in ucs["uc"] if u in texto_hist][:3] + [f"{v:.6f}" for v in ucs["latitude"] if f"{v:.6f}" in texto_hist][:3]
conferir("histórico sem nenhuma UC nem coordenada", not vazou, str(vazou))
ok = op.put(f"/api/historico/{g['id']}/municipios/3138401/texto", json={"texto": "Texto final lido na rádio."})
barrado = clientes["consulta"].put(f"/api/historico/{g['id']}/municipios/3138401/texto", json={"texto": "x"})
final = clientes["consulta"].get(f"/api/historico/{g['id']}").json()["municipios"][0].get("texto_final")
conferir("texto final: Operador grava, Consulta não (403)", ok.status_code == 200 and barrado.status_code == 403
         and final == "Texto final lido na rádio.", f"{ok.status_code} {barrado.status_code} {final}")

# ---------- 5. Admin da empresa: usuários ----------
adm = clientes["admin_empresa"]
r = adm.post("/api/usuarios", json={"nome": "Fulano de Fora", "email": "fulano@gmail.com", "perfil": "operador"})
conferir("e-mail fora do domínio da empresa é recusado", r.status_code == 422, r.text[:100])
r = adm.post("/api/usuarios", json={"nome": "Novo Operador", "email": "novo@emg.example", "perfil": "operador"})
temp_novo = r.json().get("senha_temporaria", "")
conferir("cadastro de usuário devolve a senha temporária uma vez", r.status_code == 200 and len(temp_novo) == 19, r.text[:120])
conferir("e-mail repetido é recusado (409)", adm.post("/api/usuarios", json={"nome": "Outro", "email": "novo@emg.example", "perfil": "consulta"}).status_code == 409)
lista = {x["email"]: x for x in adm.get("/api/usuarios").json()["usuarios"]}
eu_admin = lista["admin@emg.example"]["id"]
r = adm.patch(f"/api/usuarios/{eu_admin}", json={"perfil": "operador", "status": "ativo"})
conferir("último admin ativo não pode deixar de ser admin (409)", r.status_code == 409, r.text[:120])
novo_c, r = entrar("novo@emg.example", temp_novo)
r = adm.patch(f"/api/usuarios/{lista['novo@emg.example']['id']}", json={"perfil": "operador", "status": "bloqueado"})
conferir("bloquear usuário encerra a sessão dele", r.status_code == 200 and novo_c.get("/api/eu").status_code == 401)
_, r = entrar("novo@emg.example", temp_novo)
conferir("usuário bloqueado não entra (403)", r.status_code == 403, r.text[:100])

# ---------- 6. Admin do Farol: empresas e isolamento ----------
far = clientes["admin_farol"]
r = far.post("/api/empresas", json={"nome": "Cooperativa Teste", "sigla": "CTE", "dominio": "cte.example",
                                    "admin_nome": "Admin CTE", "admin_email": "admin@cte.example"})
temp_cte = r.json().get("senha_temporaria", "")
conferir("Admin do Farol cadastra empresa com o primeiro admin", r.status_code == 200 and temp_cte, r.text[:120])
cte, _ = entrar("admin@cte.example", temp_cte)
cte.post("/api/senha", json={"atual": temp_cte, "nova": NOVA})
conferir("outra empresa não vê o histórico da EMG", cte.get("/api/historico").json()["avisos"] == [])
conferir("outra empresa não altera usuário da EMG (404)", cte.patch(f"/api/usuarios/{eu_admin}", json={"perfil": "consulta", "status": "ativo"}).status_code == 404)
conferir("outra empresa não abre aviso da EMG (404)", cte.get(f"/api/historico/{g['id']}").status_code == 404)
conferir("outra empresa: dashboard vazio (não vê os avisos da EMG)", cte.get("/api/painel").json()["totais"]["avisos"] == 0)
reg_far = far.get("/api/registro").json()["registro"]
reg_adm = adm.get("/api/registro").json()["registro"]
conferir("registro: Admin do Farol vê tudo; Admin da empresa só a dele",
         any(x["empresa"] == "CTE" for x in reg_far) and all(x["empresa"] in ("EMG", None) for x in reg_adm) and any(x["acao"] == "gerou aviso" for x in reg_adm))

# ---------- 7. Bloqueio, sessão e origem ----------
for _ in range(5):
    entrar("consulta@emg.example", "senha-errada-xyz")
_, r = entrar("consulta@emg.example", NOVA)
conferir("5 senhas erradas bloqueiam a conta (mesmo com a senha certa depois: 423)", r.status_code == 423, r.text[:100])
sql("UPDATE usuario SET bloqueado_ate = NULL WHERE email = 'consulta@emg.example'")
c, _ = entrar("consulta@emg.example", NOVA)
c.post("/api/sair")
conferir("sair encerra a sessão", c.get("/api/eu").status_code == 401)
c, _ = entrar("consulta@emg.example", NOVA)
sql("UPDATE sessao SET ultimo_uso = now() - interval '9 hours'")
conferir("sessão sem uso por mais de 8 h acaba", c.get("/api/eu").status_code == 401)
c = cliente()
r = c.post("/api/entrar", json={"email": "operador@emg.example", "senha": NOVA}, headers={"Origin": "https://malicioso.example"})
conferir("login vindo de outra origem é recusado (403)", r.status_code == 403, r.text[:80])
c, _ = entrar("operador@emg.example", NOVA)
r = c.post("/api/avisos", files={"arquivo": ("p.csv", planilha)}, data={"data": "12/11", "horario": "8h"},
           headers={"Origin": "https://malicioso.example"})
conferir("envio de planilha de outra origem é recusado (403)", r.status_code == 403, r.text[:80])

# ---------- 8. Semente e o que fica no banco ----------
antes = sql("SELECT count(*) FROM usuario")[0][0]
conferir("semente de novo não cria nem altera nada", semear() == [] and sql("SELECT count(*) FROM usuario")[0][0] == antes)
hashes = [h for (h,) in sql("SELECT senha_hash FROM usuario")]
conferir("no banco, só hash Argon2id das senhas", all(h.startswith("$argon2id$") for h in hashes) and NOVA not in str(hashes))
tok = c.cookies.get(api_acesso.COOKIE)
conferir("no banco, só o hash do token da sessão", tok and not sql("SELECT 1 FROM sessao WHERE token_hash::text LIKE %s", (f"%{tok}%",)))

with conectar() as cx:
    cx.execute("DROP SCHEMA IF EXISTS teste_acesso CASCADE")
for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if extra and st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
