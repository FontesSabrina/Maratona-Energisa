# Deploy do Farol (Render + Neon, planos gratuitos)

O app roda em produção igual à máquina local: a mesma API (FastAPI) e a mesma tela, num container
Docker no Render, com o banco Postgres + PostGIS no Neon. Diferenças em produção:

- **Sem o áudio do aviso** (`FAROL_AUDIO=0`): no plano gratuito do Render (512 MB) não cabe a voz, que
  pede cerca de 520 MB a mais. A tela esconde Ouvir e Baixar áudio; o PDF e o resto funcionam.
- **Só HTTPS** (`FAROL_PRODUCAO=1`): cookie de sessão `Secure`, HSTS e sem a documentação interativa (`/api/docs`).
- O serviço gratuito **dorme** depois de um tempo sem uso; o primeiro acesso depois disso leva cerca de um minuto.
- Rede elétrica e clientes continuam **fictícios**. Antes de dado real da distribuidora: login com MFA,
  usuário próprio do banco e a avaliação da LGPD sobre onde os dados ficam (art. 33, transferência internacional).

## 1. Banco no Neon (uma vez)

1. Entre em https://neon.tech (dá para entrar com o GitHub) e crie um projeto: nome `farol`,
   Postgres 17 e, se houver, a região **AWS South America (São Paulo)**.
2. No painel do projeto, **Connect**: copie a *connection string* (`postgresql://...sslmode=require`).
3. Na raiz do projeto, crie o arquivo `.env.producao` (o git ignora) com uma linha:
   `DATABASE_URL=postgresql://...` (a string copiada). Nunca no código nem no git.
4. Leve a base pública (municípios, comunidades, endereços de referência e a rede fictícia) do banco local:
   `uv run python -m comunidades.publicar_banco`
5. Crie o acesso de produção (empresa EMG de demonstração e um usuário de cada perfil, com senha temporária
   mostrada uma vez):
   `$env:FAROL_ENV=".env.producao"; uv run python -m comunidades.semente`
   Guarde as senhas temporárias: no primeiro acesso cada usuário cria a própria.

## 2. Serviço no Render (uma vez)

1. Em https://dashboard.render.com: **New** > **Blueprint**.
2. Conecte o GitHub e escolha o repositório `lucianocs1/Maratona`. O Render lê o `render.yaml`
   (serviço `farol`, Docker, plano free, branch `master`).
3. Ele pede o valor de `DATABASE_URL`: cole a mesma string do Neon. Confirme (**Apply**).
4. O primeiro build leva alguns minutos. Quando ficar *Live*, abra o endereço que o Render mostra
   (`https://farol-....onrender.com`) e entre com um dos usuários da semente.

## 3. Depois

- **Código novo:** `git push luciano melhorias:master` (ou o que estiver na `master`): o Render refaz o deploy sozinho.
- **Base territorial ou rede refeitas** (base_concessao, rede_concessao): rode de novo o passo 1.4.
- **Senha perdida:** `$env:FAROL_ENV=".env.producao"; uv run python -m comunidades.semente --nova-senha EMAIL`.
- **Saúde:** `https://farol-....onrender.com/api/saude` mostra quantos municípios o banco tem (66).
