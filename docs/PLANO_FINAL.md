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
