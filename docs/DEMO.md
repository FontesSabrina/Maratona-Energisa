# Roteiro da demonstração (5 minutos)

Tudo com dados de demonstração: território real (IBGE), rede, clientes, rádios e histórico fictícios.

## Antes de começar (uma vez, na véspera)

1. Banco e dados prontos (README, passos 3 a 5), inclusive `uv run python -m comunidades.semente_demo` (para os relatórios terem um mês e meio de histórico).
2. Senhas: a semente mostra as senhas temporárias uma vez. Entre com cada usuário e crie a senha de cada um antes da apresentação. Senha perdida: `uv run python -m comunidades.semente --nova-senha EMAIL`.

| Perfil | E-mail |
|---|---|
| Operador | `operador@emg.example` |
| Admin da empresa | `admin@emg.example` |
| Consulta | `consulta@emg.example` |
| Admin do Farol | `admin@farol.example` |

3. Abra dois terminais: o Mailpit (`data\raw\mailpit\mailpit.exe --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025`) e a API (`uv run uvicorn comunidades.api.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers`).
4. Deixe abertas no navegador: `http://127.0.0.1:8000` (o Farol) e `http://127.0.0.1:8025` (a caixa de e-mail da rádio).
5. Planilhas em `testes/planilha/exemplos/demo/`.

## O roteiro

| Tempo | O que mostrar | O que dizer |
|---|---|---|
| 0:00 | Tela de entrar (visual Farol) | "Hoje o aviso de rádio lista fazenda por fazenda. O Farol avisa por comunidade." |
| 0:15 | Entre como **Operador**. Clique em **Ajuda**. | "Cada perfil vê só o que pode fazer, e o servidor confere tudo." |
| 0:30 | **Novo aviso** → `3_vital_rejeitado.xlsx` → data, horário, tipo "Poda de árvores" → **Conferir a planilha** | **Momento-chave:** alerta vermelho com as 2 linhas de equipamento vital (uma sem coordenada, uma fora da concessão). "Conferi" e "Gerar aviso" ficam travados. "Quem depende de aparelho para viver não pode ficar sem aviso: o Farol não deixa passar." |
| 1:15 | Volte ao passo 1 → `2_coordenadas_corrigidas.xlsx` → Conferir | 6 linhas corrigidas em roxo no mapa; os "?" explicam corrigida e rejeitada. Marque **Conferi os números e o mapa** → **Gerar aviso**. |
| 1:45 | Passo 4 (Avisos): a mensagem pelo modelo da empresa, **Ouvir**, **Baixar PDF para a rádio** | "Solicitado por Operador da EMG (Operador) · código FRL-…": tudo fica na auditoria. |
| 2:10 | **Enviar para a rádio** → Rádio Leopoldina FM (sugerida pelo alcance), valor por minuto → prévia da economia → **Enviar por e-mail** (confirmação) | Na aba do Mailpit: o e-mail com PDF e MP3 → **Confirmar recebimento** → de volta ao Farol, o envio aparece como "a rádio confirmou". |
| 3:00 | **Relatórios**: Painel do mês, Do período (custo, economia calculada x informada, % no prazo, fora do prazo) → **Baixar PDF** | "Nenhum número inventado: sem o aviso de hoje ou o custo antigo, não há economia." |
| 3:40 | Entre como **Admin da empresa**: **Rádios** (alcance por comunidade com o distrito), **Configurações** (modelo da mensagem com a prévia), **Auditoria** → **Conferir a integridade** | "A auditoria não se apaga nem se edita: cada linha guarda o código da anterior." |
| 4:20 | Entre como **Consulta**: **Mapa**, um aviso do **Histórico** → **Comprovante (PDF)** | "Quem só consulta vê os comprovantes, mas não gera nem envia nada." |
| 4:40 | Entre como **Admin do Farol**: **Empresas** (CNPJ, suspender), **Auditoria geral** | "Várias distribuidoras no mesmo Farol, cada uma isolada." |
| 5:00 | Fim | "Tudo testado: 21 baterias, 980 verificações, a matriz de cada rota com cada perfil." |

## Se sobrar tempo ou alguém perguntar

- `4_muitas_rejeicoes.xlsx`: cerca de 8% rejeitadas, acima do limite de 2%. O aviso só sai com uma justificativa, que vai para a auditoria com o nome de quem escreveu.
- `5_maliciosa_macro.xlsx`: um .xlsx com macro, recusado na porta. Nada é lido nem gravado.
- `1_correta.xlsx`: nenhum alerta. O caminho feliz em 30 segundos.
- **Tema escuro**: botão no topo; o fundo do mapa acompanha.
- **Código de verificação**: copie o FRL-… de um relatório. Na API, `/api/verificar/FRL-...` mostra quem gerou e quando.
