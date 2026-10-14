PLANO FINAL DO FAROL — execução autônoma até a apresentação (17/10)

PRIMEIRO PASSO: salve este texto inteiro em docs/PLANO_FINAL.md, commite e dê push (para qualquer sessão nova conseguir continuar). Depois execute as fases na ordem.

======== MODO DE TRABALHO ========
- Trabalhe sozinho, fase por fase, na ordem. Ao fim de cada fase: rodar os testes da fase + a regressão (testes da API, tradutor, acesso, áudio, senhas, proxy, leitura, admin e --so-algoritmo com métricas iguais às do passo 12); se tudo passar, commit + push na branch sabrina/plano-final (criada a partir da branch atual do Passo 15) e marque [x] no CHECKLIST.md.
- PARE e me pergunte SÓ se: um teste falhar e você não conseguir corrigir sem mudar o plano; as métricas do algoritmo mudarem; precisar de uma decisão que não está aqui. Nesses casos, me mostre o problema e 2-3 opções com a sua recomendação.
- Pode instalar pacotes do PyPI necessários aqui (cryptography, um gerador de PDF já usado no projeto, cliente SMTP padrão), com versões fixadas no uv.lock e sem CVE aberto. Pode baixar o Mailpit (caixa de e-mail de teste) para uso local.
- Ao fim de cada fase, escreva um resumo curto no CHECKLIST.md (o que fez, testes, commit). Se a sessão cair, a próxima sessão continua por ele.
- Arquitetura limpa (nucleo puro, banco/, api/, apresentacao/) e MVC no front. Não duplicar o que já existe: ampliar o histórico, o áudio e o login que o Luciano fez, e as telas de admin do Lucas.
- Segurança sempre: toda permissão verificada NO SERVIDOR (esconder botão não basta); segredos só em variável de ambiente; nada de dado pessoal de cliente em tela, PDF, MP3, e-mail, relatório ou log; tudo por textContent; tudo que alguém faz registrado com o NOME de quem fez (vem do login, nunca digitado).
- Dados todos fictícios. Contatos de rádio de demonstração: e-mails @example.com.

======== MATRIZ DE PERFIS (vale para todas as fases) ========
| Ação | Admin do Farol | Admin da empresa | Operador | Consulta |
| Cadastrar/suspender empresas | sim | não | não | não |
| Cadastrar/bloquear usuários da própria empresa, mudar perfil | não | sim | não | não |
| Configurações da empresa (modelo da mensagem, limite de rejeição, fuso UTM, antecedência) | não | sim | não | não |
| Cadastro de rádios (nome, e-mail, WhatsApp, comunidades, valor padrão) | não | sim | adicionar "+ Nova rádio" no envio | não |
| Importar planilha, conferir, gerar aviso, escolher tipo de desligamento | não | sim | sim | não |
| Gerar PDF e MP3, enviar para a rádio, informar valor | não | sim | sim | não |
| Baixar JSON com números de UC | não | sim | sim (auditado) | não |
| Ver mapa, histórico e comprovantes da empresa | não | sim | sim | sim |
| Relatório mensal da empresa | não | sim | sim | sim |
| Relatório de auditoria da empresa | não | sim | não | não |
| Auditoria geral de acessos (todas as empresas) | sim | não | não | não |
Cada perfil só vê na tela o que pode fazer. Teste obrigatório: para CADA rota da API e CADA perfil, conferir permitido/negado (matriz de testes). Ninguém vê dados de outra empresa.

======== FASE A — Terminar o Passo 15 (tradutor) ========
- Concluir as etapas restantes já planejadas (tela de conferência com mapa, correções destacadas, alerta vermelho de equipamento vital, caixa "Conferi os números e o mapa", justificativa quando passar do limite de rejeição, Baixar JSON/CSV).
- Criar planilhas de demonstração em testes/planilha/exemplos/demo/: uma correta, uma com coordenadas corrigidas, uma com equipamento vital rejeitado (bloqueia), uma com muitas rejeições (pede justificativa), uma maliciosa (recusada).

======== FASE B — Desligamento e registro (auditoria) ========
- Tipo de desligamento: lista (manutenção preventiva, corretiva programada, obra/ampliação da rede, poda de árvores, troca de equipamento) + "Outro" (até 200 caracteres, aviso "não escreva nome de cliente", passa na varredura). O tipo vira o {motivo} da mensagem.
- Auditoria: cada ação vira uma linha (importou, conferiu, gerou aviso, editou mensagem, gerou PDF, gerou MP3, enviou, entregue, falhou, rádio confirmou, cancelou, mudou data, baixou JSON, alterou cadastro) com data, hora, nome e perfil. Só inclusão: nada é apagado nem editado; correção = linha nova. Linhas encadeadas por hash (cada linha guarda o hash da anterior) + verificação que detecta adulteração (teste).
- PDF da rádio e histórico mostram "Solicitado por <nome> (<perfil>) em <data> às <hora> · código de verificação".

======== FASE C — Rádio (pedido oficial dos mentores) ========
- Rádios no banco, por empresa (não em TOML): nome, e-mail, WhatsApp, comunidades/municípios que alcança, valor padrão.
- Modelo de mensagem por empresa, editável pelo Admin da empresa: campos {distribuidora} {data} {inicio} {fim} {motivo} {comunidades} {comunidades_parciais} {telefone_atendimento} {codigo}; trechos opcionais entre colchetes (somem se o campo ficar vazio); nomes de comunidade lidos no ar sem sufixo de distrito. Padrão: "Atenção, ouvintes. A {distribuidora} informa: no dia {data}, das {inicio} às {fim}, haverá desligamento programado de energia para {motivo}[ nas comunidades {comunidades}].[ Ficará sem energia parte de: {comunidades_parciais}.] Programe-se.[ Dúvidas: {telefone_atendimento}.]"
- Escolha automática da(s) rádio(s) pelas comunidades afetadas (pelo nome completo com distrito) + alerta "Sem rádio cadastrada para: …". Mensagem editável antes de enviar.
- Valor por envio: rádio da lista ou "+ Nova rádio"; valor em R$ sugerido pelo último usado e editável; forma de cobrança "valor fechado pelo aviso" ou "por minuto no ar"; campo opcional "quanto custaria o aviso do jeito antigo (R$)". Valor gravado no envio (mudar o preço depois não altera o passado); registrar quem informou.
- Economia: por minuto → (segundos do aviso antigo − segundos do aviso Farol) × valor/60, calculada; valor fechado → só se a pessoa informar o custo antigo (economia informada); sempre mostrar também o tempo de ar economizado. Nunca inventar número.
- MP3 do aviso com a voz Piper já baixada (MP3, limite de tamanho; Consulta não gera).
- Envio direto por e-mail pelo servidor: PDF + MP3 anexados; confirmação "Enviar para <rádio> (<e-mail>)?"; SMTP configurável por variável de ambiente (host, porta, usuário, senha, remetente) — localmente usar o Mailpit (caixa de teste, nada sai para a internet); limite de envios por hora; status enviado/entregue/falhou na auditoria.
- No e-mail, botão "Confirmar recebimento" (link com token aleatório, uso único, expira em 7 dias) → auditoria "Rádio X confirmou em …". Sem login para a rádio.
- Alternativas: "Enviar por WhatsApp" (wa.me com texto) e "Copiar mensagem", com confirmação.
- PDF e MP3 enviados guardados CRIPTOGRAFADOS (AES-256-GCM, chave em variável de ambiente) para baixar de novo pelo histórico.

======== FASE D — Relatórios ========
- Comprovante do aviso (um por desligamento): quem pediu, quando, tipo, municípios, comunidades, nº de UCs e de equipamento vital (só contagem), rádios, envio, entrega, confirmação, custo, economia, código de verificação.
- Relatório mensal: resumo (desligamentos, avisos, comunidades, UCs, tempo no ar, custo, economia calculada/informada, tempo economizado, % no prazo), por tipo, por rádio, por comunidade (mais afetadas), avisos fora do prazo, "como a economia foi calculada", lista detalhada, comparação com o mês anterior.
- Relatório de auditoria (Admin da empresa) e auditoria geral de acessos (Admin do Farol).
- Filtros: período, município, tipo, rádio, pessoa. Exportar PDF + CSV (CSV protegido contra fórmula). Todo relatório com "gerado por <nome>" e código de verificação.
- Painel do mês: gasto, economizado, avisos, % no prazo.
- Semente de demonstração: um mês de histórico fictício (avisos, rádios, envios, confirmações) para os relatórios terem conteúdo na apresentação.

======== FASE E — Telas por perfil, visual único e Ajuda ========
- Menu e telas de acordo com a matriz de perfis (Admin do Farol: Empresas e Auditoria geral; Admin da empresa: Usuários, Rádios, Configurações + tudo do Operador + Auditoria; Operador: Novo aviso, Histórico, Relatórios; Consulta: Mapa, Histórico, Relatórios).
- Ligar as telas de admin do Lucas à API real (usuários da empresa, rádios, configurações; empresas para o Admin do Farol), sem dados em memória. Usuário: nome, e-mail do domínio da empresa, perfil, municípios, status; convite sem senha (senha temporária gerada, troca obrigatória); sem CPF/endereço/telefone pessoal; não remover o último admin.
- Visual único Farol em TODAS as telas, inclusive login e troca de senha: âmbar #F5B83D, Noite #0E1620, Maré #1C2A37, Névoa #E9EEF3, logo do farol, temas claro/escuro, alvos ≥ 44 px, funciona no celular.
- Botão "Ajuda" (explica o fluxo do perfil logado) e ícones "?" ao lado do que confunde (UC, equipamento vital, corrigida/rejeitada, limite de rejeição, localidades vizinhas, código de verificação, economia calculada × informada).

======== FASE F — Só se sobrar tempo ========
- Filtro do mapa por estado e município; selecionar polígono pronto (comunidade ou distrito) para simular desligamento; aceitar UTM/GMS também na tela de simulação; agrupar clientes por TRANSFORMADOR/CIRCUITO no mapa.
- Se não der tempo, listar no README como "Próximos passos".

======== FASE G — Fechamento ========
- README completo: o que é o Farol, como rodar (passo a passo no Windows), perfis e o que cada um faz, arquitetura (tabela MVC), segurança/LGPD (resumo do SEGURANCA.md), números de validação, próximos passos.
- SEGURANCA.md atualizado (tabela Ameaça → Proteção → Teste) e ORIGEM.md com todas as fontes, licenças e hashes.
- docs/DEMO.md: roteiro de demonstração de 5 minutos, com o login de cada perfil e as planilhas demo (incluindo o momento em que o sistema trava o equipamento vital).
- testes/rodar_testes.ps1 que roda todos os testes e mostra uma tabela final.
- Bateria final completa; commit + push; abrir Pull Request da sabrina/plano-final para a melhorias com o resumo e me mostrar o link.

======== FASE H — Relatórios completos + registro total + ficha da comunidade ========
(acrescentada em 14/10/2026; mesmo modo de trabalho das fases anteriores: etapas com teste, regressão, commit + push, só parar se travar)

H0 — Regras para TODOS os relatórios
- Rodapé em toda página: "Gerado por <nome> (<perfil>) em <data> às <hora> · Código FRL-… · página X de Y".
- Toda geração, download e envio de relatório vai para a auditoria (quem, quando, tipo, filtros, destinatários, SHA-256 do PDF).
- Segunda via: guardar cada PDF gerado CRIPTOGRAFADO (AES-256-GCM, mesma chave de arquivos) e permitir baixar a mesma via pelo histórico; o código FRL confere com o SHA-256.
- Comparações com mês anterior e mesmo mês do ano anterior (setas ↑↓ e %), quando houver dado.
- Página final "Como calculamos" com as fórmulas usadas (custo, economia calculada/informada, projeção, % no prazo, frequência e duração).
- Formatos: PDF + CSV (CSV protegido contra fórmula) + botão "Enviar" (e-mail com PDF anexo; só e-mails do domínio permitido da empresa; até 5 destinatários; limite por hora; confirmação; auditado).
- Filtros: período (mês, ano ou intervalo), município, tipo, rádio, pessoa.
- Permissões: Admin da empresa e Operador geram, baixam e enviam; Consulta só gera e baixa; Auditoria só Admin da empresa. Testar na matriz de perfis.
- O comprovante do aviso continua como está (não mexer).

H1 — Relatório mensal (diretoria)
- Resumo (1ª página): desligamentos programados, avisos gerados, pedidos às rádios (total e por canal), % confirmados pela rádio, comunidades avisadas, UCs afetadas, UCs com equipamento vital (contagem), horas totais de desligamento, tempo total no ar, gasto do mês, gasto acumulado no ano, projeção do ano, economia do mês e acumulada no ano (calculada e informada separadas), % de avisos no prazo.
- Gráficos: gasto mês a mês (jan até o mês do relatório) com linha de projeção até dezembro; avisos por semana; desligamentos por tipo.
- Seções: por tipo/motivo (qtd, UCs, horas, custo); por município; resumo por rádio; top 10 comunidades; prazos; qualidade das planilhas (importadas, linhas corrigidas/rejeitadas, bloqueios por equipamento vital, justificativas); ocorrências (cancelados e datas alteradas com quem e por quê); atividade por pessoa (avisos e envios de cada um); anexo com a lista completa de avisos do mês.

H2 — Custos por rádio (financeiro)
- Tabela do ano mês a mês (jan–dez) por rádio e total; acumulado, média mensal, projeção até dezembro (acumulado + média dos meses fechados × meses restantes, com a conta escrita).
- Orçamento anual de rádio (novo campo nas Configurações, Admin da empresa): % usado e alerta se a projeção passar do orçamento.
- Por rádio: pedidos, segundos no ar, valor cobrado (mín/máx/variação), custo total, custo médio por aviso, economia calculada/informada, % de confirmação.
- Ranking das rádios por custo; alerta de preço quando um envio custar mais de 20% acima da média da própria rádio (configurável).
- Conferência de fatura: lista de cada envio por rádio (data, aviso, valor, forma de cobrança, quem informou) para bater com a nota da rádio.
- Envios sem confirmação da rádio.

H3 — Comunidades mais afetadas (planejamento)
- Ranking por nº de desligamentos e por horas sem luz; município e distrito.
- Tabela comunidade × tipo/motivo.
- Evolução mensal das top 10.
- Repetição: comunidades com 3+ desligamentos em 30 dias (configurável) e intervalo médio entre desligamentos.
- UCs afetadas e equipamento vital (só contagens); rádios que cobrem e % de confirmação.
- Sugestões automáticas em texto (ex.: "<comunidade> teve N desligamentos por <tipo> em 60 dias: avaliar juntar os serviços").

H4 — Prazos (regulação)
- Regra aplicada (antecedência mínima e prazo de equipamento vital, da configuração).
- % no prazo mês a mês, por município, por tipo e por pessoa.
- Lista dos fora do prazo: data do aviso, data do desligamento, antecedência real × exigida, justificativa, quem gerou.
- Risco: envios não confirmados pela rádio com desligamento nos próximos 3 dias.

H5 — Auditoria (Admin da empresa) e auditoria geral (Admin do Farol)
- Todas as ações filtráveis por pessoa, tipo e período; logins (sucesso, falha, bloqueio); alterações de cadastro com antes → depois (rádios, valores, usuários, configurações); downloads de JSON com UC; relatórios gerados/enviados e destinatários; verificação da cadeia ("Cadeia de registros verificada ✓" ou o ponto onde quebrou); resumo por usuário.

H6 — Registro total
- Conferir que TODA ação que cria, altera, envia, baixa ou gera arquivo grava na auditoria com nome e perfil (inclusive: gerar PDF/MP3, gerar/baixar/enviar relatório, mudar configuração, valor de rádio, orçamento, cancelar/mudar data). Teste que percorre todas as rotas que alteram algo e falha se alguma não gravar auditoria.
- O histórico de cada aviso mostra a linha do tempo completa com nomes.

H7 — Ficha da comunidade e incrementos (se der tempo depois de H0–H6)
- Clique no contorno da comunidade no mapa do app: painel com nome, distrito, município, UCs e equipamento vital (contagens), rádios que alcançam; se houver aviso aberto, os afetados (inteira/parte); histórico de 12 meses (nº de desligamentos, horas sem luz, mini gráfico mensal, último e próximo, tipos mais comuns, % no prazo, comparação com o mês anterior); botão "Relatório desta comunidade (PDF)" com Enviar. Se o app não desenha o contorno, usar o contorno estimado do mapa antigo com o aviso "contorno aproximado".
- Mapa de calor por quantidade de desligamentos (legenda, temas claro/escuro).
- Alerta de repetição ao gerar aviso (amarelo, não bloqueia, registrado na auditoria).

Semente de demonstração: completar com dados fictícios de janeiro até hoje (avisos, envios com valores variados, uma rádio com preço acima da média, comunidades com repetição, alguns fora do prazo, alguns sem confirmação), para todos os relatórios terem conteúdo. Atualizar docs/DEMO.md com um passo dos relatórios (custos com projeção e orçamento) e da ficha da comunidade.

Testes: unidade das contas (projeção, orçamento, economia, % no prazo, frequência, duração, comparações), PDF gerado para cada relatório com rodapé e código, segunda via idêntica (mesmo SHA-256), envio só para o domínio permitido, matriz de perfis, varredura de minimização em todos os PDFs/CSV/e-mails, teste "toda rota que altera grava auditoria". Métricas do algoritmo iguais. Ao fim: resumo curto + atualizar o PR.
