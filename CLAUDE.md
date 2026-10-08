# Contexto do projeto

Desafio 3 da Maratona TIVIT-RPV (Grupo Energisa): "Fazenda por fazenda, ou uma comunidade só?". O app identifica as comunidades afetadas por um desligamento programado para que o aviso no rádio cite comunidades, e não fazenda por fazenda. Apresentação em 17/10/2026.

## Decisões já tomadas (não mudar sem perguntar)
- Desenvolvemos em cima deste repositório. Nada de reescrever do zero.
- O mapa continua sendo um HTML estático (Leaflet), sem servidor e sem Streamlit. Os dados pesados são pré-calculados no Python.
- Quem é afetado é decidido pela rede elétrica (UCs a jusante da chave aberta), nunca por distância ou raio.
- O gabarito do IBGE só pode ser lido em validacao/avaliacao.py. O algoritmo nunca pode usá-lo.
- A rede elétrica e os clientes são fictícios; os dados do IBGE, CNEFE e OSM são reais. Toda tela e texto devem deixar isso claro.
- LGPD: nada de nomes de pessoas em telas de aviso; para cargas sensíveis, só contagens.
- O aviso de rádio é o produto central. Recursos novos complementam o rádio, não o substituem.
- Prazos de aviso: 72 horas para a maioria das unidades e 5 dias úteis para quem usa equipamento vital (REN 1.000/2021, art. 436). A empresa tem um prazo interno de planejamento de cerca de 15 dias (a confirmar), que deve ser configurável.
- Arquitetura: o projeto está organizado em fontes/ (dados reais), simulacao/ (dados fictícios), nucleo/ (regras do produto, sem depender de onde vêm os dados), validacao/ (métricas e testes) e apresentacao/ (mapa, PDF e tela). Código novo já deve respeitar essa separação: o nucleo não lê arquivos nem conhece o IBGE.
- Segurança e LGPD: minimização de dados. Nada de nome de titular, número de UC ou endereço em telas, no HTML gerado ou em PDFs; só comunidades, classes e contagens. O HTML gerado não pode chamar nenhum servidor além dos de fundo de mapa. Nenhum segredo, senha ou chave no código ou no git. O texto do aviso atual (fazenda a fazenda) pode listar nomes de imóveis e ruas, porque reproduz o comunicado público que já é transmitido no rádio; ele nunca inclui nomes de pessoas, números de UC nem coordenadas.

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
- Teste de robustez: py -m uv run python -m comunidades.validacao.robustez
- Janela de menor dano (ramais rurais, perfis hipotéticos): py -m uv run python -m comunidades.validacao.janela

## Referências para comparação (desde o passo 12)
- Métricas: saida/metricas_passo12.txt (Leopoldina) e saida/muriae/metricas_passo12.txt (Muriaé), iguais às do passo 10b. São a referência de "antes e depois".
- Avisos e janelas para os testes JS × Python: saida/referencias_passo12/ e saida/muriae/referencias_passo12/ (avisos.json: avisos pt-BR e nos 3 idiomas; janelas.json: 3 sugestões por chave, 2 datas e 3 durações; areas.json: 200 áreas sorteadas com o resultado esperado). Gerados pelo Python; o navegador tem de reproduzi-los exatamente.
- Regenerar: py -m uv run python -m comunidades.validacao.referencias e py -m uv run python -m comunidades.validacao.area (com $env:FAROL_DISTRIBUIDORA para Muriaé).
- No passo 12, resumir() passou a ordenar de forma estável (empate no número de UCs afetadas: ordem alfabética). Só mudou a ordem de comunidades empatadas em 30 avisos de Leopoldina e 21 de Muriaé; as referências do passo 10b (saida/referencias_passo10b/, saida/metricas_passo10b.txt) ficam guardadas para consulta.
- Esses arquivos ficam fora do git (saida/ é ignorada): se faltarem, regenere rodando o pipeline e grave de novo.

## Regras de trabalho
- Explique o plano antes de editar e espere minha confirmação.
- Mudanças pequenas e testadas, uma etapa por vez.
- Depois de cada mudança que afete o algoritmo ou o aviso, rode --so-algoritmo e mostre as métricas antes e depois.
- Código e comentários em português, seguindo o estilo dos arquivos existentes.
- Nunca invente números para o README ou para o pitch: só use números que o pipeline imprimiu.
