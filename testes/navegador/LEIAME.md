# Testes do navegador

Conferem se o mapa (`saida/mapa_comunidades.html`) e a página de entrada (`saida/index.html`), abertos num navegador de verdade, fazem exatamente as mesmas contas que o Python e mostram a mesma tela de antes. O navegador abre sem janela, com um perfil descartável. Nada é instalado e nada vai para a internet além dos fundos de mapa.

Os testes esperam o mapa ficar pronto (a tela de abertura some quando ele termina de montar) antes de começar.

## O que cada arquivo confere

- **`teste_equivalencia.mjs`** compara o JavaScript do mapa com as referências geradas pelo Python, em `saida/referencias_passo12/`:
  - **Por chave:** o aviso pt-BR, o aviso de hoje, o aviso nos 3 idiomas (2 datas e horários) e as 3 janelas sugeridas (2 datas e 3 durações), para todas as chaves. Também o tamanho do aviso de hoje (locais, palavras e segundos) calculado pelos códigos de local, como no modo área, contra o contado no texto pelo Python.
  - **Por área:** 200 áreas sorteadas, mais uma fora do município e uma que engloba o município inteiro. Para cada uma: a situação, as UCs dentro, as comunidades e a classificação, o aviso nos 3 idiomas, as cargas sensíveis, os alimentadores, as janelas, o tamanho do aviso de hoje e o resumo do código de verificação.
  - **Ponto da obra:** 200 pontos sorteados (perto da rede, longe, fora do município e no tronco), com o trecho, a distância e as chaves que desligam o trecho.
  - Também acusa exceções na página e violações da CSP.
- **`teste_tela.mjs`** confere que uma reorganização do código não mudou nada na tela:
  - Tira um "retrato" de tudo o que o mapa mostra: a lateral (com o que está visível), a busca, a legenda, o popup, o roteiro do PDF (sem a hora de geração e o código), todas as camadas do mapa e o enquadramento.
  - O retrato é feito em cada chave, nos 200 pontos da obra e nas 202 áreas, e numa amostra delas com troca de idioma, aba, janela, horário, telefone, tema e modo apresentação.
  - Com `--gravar`, grava a referência (`tela.json`); sem, compara com ela. A referência atual foi gravada na versão do passo 12, antes da organização em MVC.
- **`teste_interface.mjs`** testa o modo área com cliques de verdade (só Leopoldina). São 39 verificações:
  - **Desenho perto da CF-0066:** desenhar, desfazer e concluir, sem abrir popups.
  - **Importação** do GeoJSON de exemplo.
  - **Segurança:** o KML com HTML e script na descrição não injeta nada na página.
  - **Mensagens de erro:** 11 casos (arquivo vazio, formato, JSON inválido, sem polígono, coordenadas fora de graus, fora do município, sem clientes, vértices demais, mais de 5 MB, KML malformado).
  - **Download** do GeoJSON sem exceção na CSP.
  - **PDF:** registro da área e código de verificação recalculado fora do navegador.
  - **Troca de modo:** voltar ao modo por chave mantém tudo como antes.
  - **Celular:** nenhuma rolagem horizontal a 390 px.
  - Grava as capturas e os PDFs em `saida/capturas_passo12/`.
- **`teste_abertura.mjs`** testa a tela de abertura, a página de entrada e o botão "Trocar área":
  - **Abertura do mapa:** com a CPU desacelerada, registra quadro a quadro o que a tela mostrava. A abertura tem de ser a primeira coisa desenhada, mostrar "Carregando o território…", "Montando a rede…" e "Pronto", nessa ordem, e sumir sozinha quando o mapa fica pronto.
  - **Movimento reduzido:** sem animação do feixe, e a abertura some na hora.
  - **Entrada:** um cartão por município com links relativos, nenhum script, CSP com `script-src 'none'`, a nota de dados fictícios, a animação só com CSS em cerca de 1,2 s e nenhuma rolagem horizontal.
  - **Navegação:** "Abrir" leva ao mapa certo, e "Trocar área" volta à entrada, nas duas cidades.
  - Grava as capturas em `saida/capturas_passo13/`.
- **`varredura_44px.mjs`** procura botões, links e campos visíveis com menos de 44 × 44 px no mapa (inicial, camadas, chave, abas, popup, busca, ponto da obra, área e desenho) e na página de entrada, no computador e no celular.
- **`cdp.mjs`** abre o navegador e conversa com ele pelo DevTools Protocol. Os outros testes usam este arquivo.
- **`exemplos/`** tem os contornos usados no teste de interface. São cópias dos que ficam em `saida/exemplos/`, que não vai para o git.

## O que precisa estar instalado

- **Node.js 22 ou mais novo**, que já traz `fetch` e `WebSocket`. Não há pacote npm para instalar.
- **Microsoft Edge ou Google Chrome.** O teste procura nos caminhos padrão do Windows. Se o navegador estiver em outro lugar, informe o caminho:
  `$env:FAROL_NAVEGADOR="C:\caminho\msedge.exe"`
- **O mapa, a entrada e as referências já gerados.** Rode estes comandos antes, uma vez por município:

```powershell
py -m uv run comunidades --so-algoritmo
py -m uv run python -m comunidades.validacao.referencias
py -m uv run python -m comunidades.validacao.area
py -m uv run python -m comunidades.validacao.obra
```

Para Muriaé, defina `$env:FAROL_DISTRIBUIDORA="distribuidoras/demo-muriae.toml"` antes dos três últimos comandos e use `--distribuidora distribuidoras/demo-muriae.toml` no primeiro.

## Como rodar (Windows, PowerShell, na raiz do projeto)

```powershell
node testes/navegador/teste_equivalencia.mjs              # Leopoldina
node testes/navegador/teste_equivalencia.mjs saida/muriae # Muriaé
node testes/navegador/teste_tela.mjs                      # Leopoldina (saida/muriae para Muriaé)
node testes/navegador/teste_interface.mjs                 # interface do modo área (Leopoldina)
node testes/navegador/teste_abertura.mjs                  # abertura, entrada e "Trocar área"
node testes/navegador/varredura_44px.mjs                  # alvos de toque (saida/muriae para Muriaé)
```

Cada teste termina com código 0 quando está tudo certo e 1 quando há diferença. O resultado esperado é:
- 0 erros no teste de equivalência;
- 0 retratos diferentes no teste de tela;
- "39 de 39 verificações OK" no teste de interface;
- todas as verificações OK no teste de abertura;
- "Nenhum alvo de toque abaixo de 44 px" na varredura.
