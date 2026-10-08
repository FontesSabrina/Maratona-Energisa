# Testes do navegador

Conferem se o mapa (`saida/mapa_comunidades.html`), aberto num navegador de verdade, faz exatamente as mesmas contas que o Python. O navegador abre sem janela, com um perfil descartável. Nada é instalado e nada vai para a internet além dos fundos de mapa.

## O que cada arquivo confere

- **`teste_equivalencia.mjs`** compara o JavaScript do mapa com as referências geradas pelo Python, em `saida/referencias_passo12/`:
  - **Por chave:** o aviso pt-BR, o aviso de hoje, o aviso nos 3 idiomas (2 datas e horários) e as 3 janelas sugeridas (2 datas e 3 durações), para todas as chaves.
  - **Por área:** 200 áreas sorteadas, mais uma fora do município e uma que engloba o município inteiro. Para cada uma: a situação, as UCs dentro, as comunidades e a classificação, o aviso nos 3 idiomas, as cargas sensíveis, os alimentadores, as janelas e o resumo do código de verificação.
  - Também acusa exceções na página e violações da CSP.
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
- **`cdp.mjs`** abre o navegador e conversa com ele pelo DevTools Protocol. Os outros dois usam este arquivo.
- **`exemplos/`** tem os contornos usados no teste de interface. São cópias dos que ficam em `saida/exemplos/`, que não vai para o git.

## O que precisa estar instalado

- **Node.js 22 ou mais novo**, que já traz `fetch` e `WebSocket`. Não há pacote npm para instalar.
- **Microsoft Edge ou Google Chrome.** O teste procura nos caminhos padrão do Windows. Se o navegador estiver em outro lugar, informe o caminho:
  `$env:FAROL_NAVEGADOR="C:\caminho\msedge.exe"`
- **O mapa e as referências já gerados.** Rode estes comandos antes, uma vez por município:

```powershell
py -m uv run comunidades --so-algoritmo
py -m uv run python -m comunidades.validacao.referencias
py -m uv run python -m comunidades.validacao.area
```

Para Muriaé, defina `$env:FAROL_DISTRIBUIDORA="distribuidoras/demo-muriae.toml"` antes dos dois últimos comandos e use `--distribuidora distribuidoras/demo-muriae.toml` no primeiro.

## Como rodar (Windows, PowerShell, na raiz do projeto)

```powershell
node testes/navegador/teste_equivalencia.mjs              # Leopoldina
node testes/navegador/teste_equivalencia.mjs saida/muriae # Muriaé
node testes/navegador/teste_interface.mjs                 # interface do modo área (Leopoldina)
```

Cada teste termina com código 0 quando está tudo certo e 1 quando há diferença. O resultado esperado é 0 erros no teste de equivalência e "39 de 39 verificações OK" no teste de interface.
