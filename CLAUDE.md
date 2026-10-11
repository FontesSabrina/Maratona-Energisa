# Contexto do projeto

Desafio 3 da Maratona TIVIT-RPV (Grupo Energisa): "Fazenda por fazenda, ou uma comunidade só?". O app identifica as comunidades afetadas por um desligamento programado para que o aviso no rádio cite comunidades, e não fazenda por fazenda. Desde 11/10/2026 o objetivo é um produto profissional (não mais só a demonstração da maratona), preparado para receber dados reais da distribuidora.

## Decisões já tomadas (não mudar sem perguntar)
- Desenvolvemos em cima deste repositório. Nada de reescrever do zero.
- Arquitetura em fases (desde 11/10/2026): app do mapa (frontend) + API em Python (FastAPI) + Postgres. Sem Streamlit. Os dados públicos pesados (base territorial do IBGE) continuam pré-calculados no Python. O mapa estático atual (saida/) fica como demonstração até o app novo substituí-lo.
- Quem é afetado vem da planilha de UCs afetadas que a distribuidora envia (UC + coordenada; ver "Planilha de UCs" abaixo). O município sai da coordenada (malha do IBGE) e a comunidade sai do algoritmo. Nunca por raio ou distância em volta de um ponto.
- A rede elétrica fictícia e o modo "abrir uma chave" saem do fluxo principal: ficam só como demonstração e para gerar planilhas de teste.
- O gabarito do IBGE só pode ser lido em validacao/ (avaliacao.py e planilha.py). O algoritmo do cadastro (nucleo/algoritmo.py) nunca pode usá-lo.
- Desde 11/10/2026, no modo planilha, a base territorial (contorno, nome e tamanho de cada comunidade) vem do CNEFE limpo (fontes/base_territorial.py), o mesmo de onde sai o gabarito. Regra: nunca validar com os mesmos endereços que montaram a base (validacao/planilha.py: amostra separada de 20% e planilhas de teste em 5 partes).
- Hoje a rede elétrica e os clientes são fictícios; os dados do IBGE, CNEFE e OSM são reais. Toda tela e texto devem deixar isso claro. Dados reais de clientes vão entrar: a planilha é dado pessoal desde já.
- LGPD: nada de nomes de pessoas em telas de aviso; para cargas sensíveis, só contagens.
- O aviso de rádio é o produto central. Recursos novos complementam o rádio, não o substituem.
- Prazos de aviso: 72 horas para a maioria das unidades e 5 dias úteis para quem usa equipamento vital (REN 1.000/2021, art. 436). A empresa tem um prazo interno de planejamento de cerca de 15 dias (a confirmar), que deve ser configurável.
- Arquitetura: o projeto está organizado em fontes/ (dados reais), simulacao/ (dados fictícios), nucleo/ (regras do produto, sem depender de onde vêm os dados), validacao/ (métricas e testes), apresentacao/ (mapa, PDF e tela) e banco/ (Postgres: conexão pelo DATABASE_URL e as tabelas). Código novo já deve respeitar essa separação: o nucleo não lê arquivos nem conhece o IBGE.
- Segurança e LGPD: minimização de dados. Nada de nome de titular, número de UC ou endereço em telas, no HTML gerado ou em PDFs; só comunidades, classes e contagens. O frontend só fala com a própria API (CSP connect-src 'self') e com os servidores de fundo de mapa; o mapa estático de demonstração continua sem nenhuma conexão (connect-src 'none'). Nenhum segredo, senha ou chave no código ou no git: credenciais só em variável de ambiente (.env, ignorado pelo git; DATABASE_URL para o banco).
- A planilha é processada em memória e descartada. O banco guarda só o resultado agregado (municípios, comunidades, contagens e o aviso), nunca número de UC nem coordenada. Login e perfis entram antes de qualquer dado real. O texto do aviso atual (fazenda a fazenda) pode listar nomes de imóveis e ruas, porque reproduz o comunicado público que já é transmitido no rádio; ele nunca inclui nomes de pessoas, números de UC nem coordenadas.

## Planilha de UCs (modelo provisório, até a distribuidora mandar o oficial)
- Colunas: uc (obrigatória, texto), latitude e longitude (obrigatórias, graus decimais, vírgula ou ponto), equipamento_vital (opcional, sim/não: prazo de 5 dias úteis) e classe (opcional: residencial, rural, comercial...).
- Formatos .xlsx e .csv; até 50 mil linhas e 10 MB. A tela oferece o modelo para baixar.
- A validação aponta, pela linha e sem mostrar a UC: sem coordenada, coordenada fora da área de concessão e UC repetida.

## Banco de dados
- Postgres 17 local, banco fazendadb. A conexão vem de DATABASE_URL no .env (nunca no código). O usuário postgres é superusuário: antes de publicar, criar um usuário próprio do app e trocar a senha.
- PostGIS 3.6.2 instalado e ativo no fazendadb (CREATE EXTENSION postgis): as geometrias da base territorial ficam no banco em colunas geometry (SIRGAS 2000, EPSG:4674).

## Arquitetura e MVC
As pastas seguem uma arquitetura em camadas, parente do MVC, que além de separar regras, tela e orquestração também separa os dados reais (fontes/) dos fictícios (simulacao/).

| MVC | No projeto |
|---|---|
| Model | nucleo/ (regras) + fontes/ e simulacao/ (dados) e o Model do JavaScript do mapa (estado da tela e regras puras) |
| View | apresentacao/ (mapa, página de entrada e PDF) e a View do JavaScript do mapa |
| Controller | pipeline.py e o Controller do JavaScript do mapa |

- O script do mapa (apresentacao/mapa_template.html) tem três partes, marcadas por comentário: o Model (objeto `estado` e regras puras, sem tocar no HTML), a View (desenha lateral, mapa, PDF e tela de abertura a partir do estado, sem mudar o estado) e o Controller (eventos e abertura; atualiza o estado e pede à View para redesenhar).
- A página de entrada (saida/index.html) é gerada por apresentacao/entrada.py a partir dos resumo_mapa.json que cada mapa grava (só município, UF, código IBGE e contagens). Mostra o mapa do Brasil (Leaflet) com o contorno da concessão (distribuidoras/concessao/EMG.kml, lido por fontes/concessao.py, só a geometria) e os municípios dentro dela (malha do IBGE, data/raw/malhas). O script segue o mesmo Model, View e Controller do mapa, liberado por hash na CSP; os cartões abaixo do mapa funcionam sem script.

## Configuração da distribuidora
- Tudo o que muda de uma distribuidora para outra (nome, telefone, município, prazos, expediente, limites do aviso e perfis de sensibilidade) fica em distribuidoras/demo-leopoldina.toml. Para outra empresa, copiar distribuidoras/MODELO.toml.
- O pipeline lê esse arquivo (src/comunidades/distribuidora.py) e passa os valores ao nucleo; o nucleo não lê arquivos. Outra configuração: py -m uv run comunidades --distribuidora distribuidoras/arquivo.toml
- Os modelos do aviso por idioma (pt-BR, en, es) ficam em src/comunidades/nucleo/idiomas.py.
- O município (codigo_ibge, municipio, uf) também vem desse arquivo: dele saem os downloads do IBGE, a projeção UTM, a sigla da rede fictícia (ou sigla_rede, opcional) e as pastas. Leopoldina fica em data/interim, data/sintetico e saida/; os outros em data/<municipio>/ e saida/<municipio>/.
- Outro município: py -m uv run comunidades --distribuidora distribuidoras/demo-muriae.toml, ou por coordenada: py -m uv run comunidades --coordenada "-21.13,-42.37" (se não houver arquivo para o município, cria distribuidoras/auto-<municipio>.toml para revisar).
- Avaliação, robustez e janela de outro município: $env:FAROL_DISTRIBUIDORA="distribuidoras/demo-muriae.toml" antes do comando.

## Como rodar (Windows)
- Pipeline completo: py -m uv run comunidades
- Só algoritmo, avaliação e mapa: py -m uv run comunidades --so-algoritmo
- Avaliação detalhada: py -m uv run python -m comunidades.validacao.avaliacao
- Base territorial dos 66 municípios da concessão no banco (CNEFE limpo, sem OSM e sem rede fictícia; um processo por município, os que faltam): uv run python -m comunidades.base_concessao (--refazer para todos, --so cod1,cod2 para alguns)
- Avaliação do modo planilha (amostra separada e planilhas de teste por chave, lado a lado com o algoritmo atual): py -m uv run python -m comunidades.validacao.planilha (depois do pipeline; grava saida/avaliacao_planilha.csv)
- API (FastAPI, só na própria máquina até existir login): uv run uvicorn comunidades.api.app:app --host 127.0.0.1 --port 8000 (documentação interativa em http://127.0.0.1:8000/api/docs; depois de rodar o base_concessao de novo, reinicie a API)
- Tela do app (envio da planilha, avisos editáveis por município, mapa das comunidades e PDF para a rádio): http://127.0.0.1:8000/ com a API rodando. Arquivos em apresentacao/app/ (index.html, app.css, app.js em Model, View e Controller; nada embutido, CSP só 'self' pelo cabeçalho da API).
- Teste da tela (aviso igual ao da API, mapa, edição, PDF, nenhuma UC ou coordenada na página, só requisições ao próprio servidor e à Esri, 44 px, celular): node testes/navegador/teste_app.mjs (com a API rodando; capturas e PDF em saida/capturas_app/)
- Teste da API (banco x arquivo, csv x xlsx, dois municípios, problemas por linha, erros, nenhuma UC ou coordenada na resposta): uv run python -W ignore testes/api/teste_api.py
- Planilhas de teste (UCs fictícias a jusante de uma chave, em saida/planilhas_teste/): uv run python -m comunidades.simulacao.planilhas_teste CF-0066 [--ruido 15]
- Nesta máquina o comando py não existe: use uv run direto (uv run comunidades, uv run python -m ...)
- Varredura de minimização (titular, número de UC, imóvel e logradouro no HTML gerado): py -m uv run python -m comunidades.validacao.minimizacao (com $env:FAROL_DISTRIBUIDORA para Muriaé)
- Teste de robustez: py -m uv run python -m comunidades.validacao.robustez
- Janela de menor dano (ramais rurais, perfis hipotéticos): py -m uv run python -m comunidades.validacao.janela
- Página de entrada (lista os municípios já gerados): py -m uv run python -m comunidades.apresentacao.entrada (o pipeline já gera no fim)
- Testes do navegador: ver testes/navegador/LEIAME.md

## Referências para comparação (desde o passo 12)
- Métricas: saida/metricas_passo12.txt (Leopoldina) e saida/muriae/metricas_passo12.txt (Muriaé), iguais às do passo 10b. São a referência de "antes e depois".
- Avisos e janelas para os testes JS × Python: saida/referencias_passo12/ e saida/muriae/referencias_passo12/ (avisos.json: avisos pt-BR e nos 3 idiomas; janelas.json: 3 sugestões por chave, 2 datas e 3 durações; areas.json: 200 áreas sorteadas com o resultado esperado; obra.json: 200 pontos da obra sorteados, desde o passo 13; tamanho_hoje.json: locais, palavras e segundos do aviso de hoje por chave, e esperado.hoje em areas.json, desde o passo 14). Gerados pelo Python; o navegador tem de reproduzi-los exatamente.
- Regenerar: py -m uv run python -m comunidades.validacao.referencias, py -m uv run python -m comunidades.validacao.area e py -m uv run python -m comunidades.validacao.obra (com $env:FAROL_DISTRIBUIDORA para Muriaé).
- Tela (desde o passo 13): tela.json nas mesmas pastas, gravado pelo testes/navegador/teste_tela.mjs --gravar a partir da versão do passo 12 (antes do MVC). É o retrato de tudo o que a tela mostra em cada chave, ponto da obra e área; uma reorganização do código tem de manter tudo idêntico. Só regrave quando uma mudança de tela for intencional.
- No passo 12, resumir() passou a ordenar de forma estável (empate no número de UCs afetadas: ordem alfabética). Só mudou a ordem de comunidades empatadas em 30 avisos de Leopoldina e 21 de Muriaé; as referências do passo 10b (saida/referencias_passo10b/, saida/metricas_passo10b.txt) ficam guardadas para consulta.
- Esses arquivos ficam fora do git (saida/ é ignorada): se faltarem, regenere rodando o pipeline e grave de novo.

## Regras de trabalho
- Explique o plano antes de editar e espere minha confirmação.
- Mudanças pequenas e testadas, uma etapa por vez.
- Depois de cada mudança que afete o algoritmo ou o aviso, rode --so-algoritmo e mostre as métricas antes e depois.
- Em todo passo que mexer no HTML (mapa, entrada ou dados que vão para eles), rode a varredura de minimização (validacao/minimizacao.py) nas duas cidades; ela tem de terminar sem nenhuma ocorrência proibida.
- Código e comentários em português, seguindo o estilo dos arquivos existentes.
- Nunca invente números para o README ou para o pitch: só use números que o pipeline imprimiu.
