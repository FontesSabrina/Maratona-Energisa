# Checklist do plano final (docs/PLANO_FINAL.md)

Branch: sabrina/plano-final (a partir da sabrina/passo15-tradutor, commit ee9b030).
Uma sessão nova continua daqui: ler docs/PLANO_FINAL.md e a última fase sem [x].

- [x] Passo 0: plano salvo em docs/PLANO_FINAL.md e este checklist criados
- [x] Fase A: terminar o Passo 15 (tela de conferência, planilhas demo)
- [x] Fase B: tipo de desligamento e auditoria encadeada por hash
- [x] Fase C: rádios, modelo de mensagem, envio por e-mail, confirmação, arquivos criptografados
- [x] Fase D: comprovante, relatório mensal, relatórios de auditoria, painel do mês, semente de demonstração
- [x] Fase E: telas por perfil, visual único Farol, Ajuda
- [x] Fase F: só se sobrar tempo (filtros do mapa, polígono pronto, UTM/GMS na simulação, transformador/circuito) — parcial, ver resumo
- [x] Fase G: README, SEGURANCA.md, ORIGEM.md, docs/DEMO.md, testes/rodar_testes.ps1, PR para a melhorias
- [x] Fase H: relatórios completos, registro total, ficha da comunidade
  - [x] H0 regras dos relatórios (rodapé, segunda via, comparações, Como calculamos, PDF/CSV/Enviar, filtros, permissões)
  - [x] H1 mensal (diretoria)
  - [x] H2 custos por rádio
  - [x] H3 comunidades mais afetadas
  - [x] H4 prazos
  - [x] H5 auditoria e auditoria geral
  - [x] H6 registro total e linha do tempo do aviso
  - [x] H7 ficha da comunidade, mapa de calor, alerta de repetição
  - [x] Semente do ano, DEMO.md, PR atualizado
- [ ] Fase J: verificação geral (todo botão funciona, tudo salva)
  - [ ] J1 inventário (docs/VERIFICACAO.md)
  - [ ] J2 teste de ponta a ponta por item e por perfil
  - [ ] J3 erros corrigidos com teste
  - [ ] J4 cadastro de rádio só do Admin da empresa + pedidos de rádio
- [ ] Fase K: idiomas (pt-BR, en, es)
  - [ ] K1 aviso, mensagem, tipos, PDF, e-mail, comprovante e áudio nos 3 idiomas
  - [ ] K2 telas nos 3 idiomas
- [ ] Fase I: acessibilidade e todos os equipamentos
  - [ ] I1 layout por tamanho de tela
  - [ ] I2 texto, cor e movimento
  - [ ] I3 teclado e leitor de tela
  - [ ] I4 tempo e trabalho perdido
  - [ ] I5 testes automáticos (axe, teclado, reflow, contraste)
  - [ ] I6 botão Acessibilidade (prioridade 2)
  - [ ] I7 Libras e voz (prioridade 2)
  - [ ] I8 declaração e retorno (prioridade 2)

## Resumos por fase

### Passo 0 (14/10/2026)
- Plano salvo; checklist criado. Ficou fora deste commit, no diretório de trabalho, a etapa 4 do Passo 15 em andamento (api/conferencia.py e testes/planilha/teste_conferencia.py): ela entra na Fase A.

### Fase A (14/10/2026)
- Feito: dupla conferência independente (api/conferencia.py, etapa 4 do Passo 15); planilha em dois passos: POST /api/planilha (Conferir, nada no histórico) e POST /api/avisos (Gerar) com pacote assinado (api/pacote.py: HMAC, FAROL_CHAVE_PACOTE, 15 min, preso a usuário e empresa, UCs opacas); travas puras (nucleo/travas.py): equipamento vital rejeitado/corrigido/fora bloqueia sempre, limite de rejeição com justificativa (300 car.), suspeitos amarelos (isolado, muitas UCs na mesma coordenada, município diferente da maioria), caixa "Conferi os números e o mapa"; Baixar JSON com UCs (permissão baixar_json, auditado) e relatório CSV protegido contra fórmula; erro inesperado = "nada foi gerado (ERR-xxxx)", log sem dados; segredos.py (env ou .env); tela do passo 3 com a conferência, alertas, corrigidas em roxo no mapa, escolha de aba; 5 planilhas demo (simulacao/planilhas_demo.py, reprodutíveis byte a byte).
- Testes: teste_travas 48/48, teste_demo 6/6, teste_api 76/76, teste_acesso 36/36, navegador (rodar_teste_app) 76/76, coordenadas 105, tradutor 67, conferencia 15, nucleo/planilha 67, proxy 15, leitura 51, senhas 11, áudio 15, admin 182; minimização sem ocorrência nas duas cidades; --so-algoritmo igual ao passo 12 (Rural 0.561→0.912, Urbana 0.852→0.956, 835 cenários, 88.3%/95.0%, 44s→14s).
- Commit: ver git log ("Fase A").

### Fase B (14/10/2026)
- Feito: auditoria só inclusão (gatilhos UPDATE/DELETE/TRUNCATE no banco) e encadeada por hash (nucleo/auditoria.py), com nome e perfil copiados do login; migração das linhas antigas; /api/auditoria/verificar (Admin do Farol vê onde quebrou; Admin da empresa só se está íntegra); código de verificação FRL-… do aviso = hash da linha "gerou aviso" (mesma transação), /api/verificar/{codigo}; tipo de desligamento (lista + "Outro" sem dado pessoal), guardado no aviso; cancelar e mudar a data pelo histórico (auditoria com antes e depois); "gerou PDF", "editou a mensagem", "gerou MP3" na auditoria; "Solicitado por <nome> (<perfil>) em <data> às <hora> · código" no aviso, no histórico e no PDF; Consulta sem o PDF da rádio; aba "Auditoria" com "Conferir a integridade"; teste_matriz (toda rota x todo perfil, rota nova sem regra = falha); testes/rodar_testes.ps1.
- Testes: teste_auditoria 45/45, teste_matriz 5/5 (28 rotas fechadas x 4 perfis + sem login + isolamento), navegador 84/84, API 76/76, acesso 36/36 e o resto da bateria (rodar_testes.ps1: 19 de 19); --so-algoritmo igual ao passo 12.
- Próximo: Fase C. O PDF ainda sai da impressão do navegador; na Fase C ele passa a ser gerado no servidor (anexo do e-mail), e aí a permissão de gerar PDF fica garantida no servidor.

### Fase C (14/10/2026)
- Feito: rádios por empresa no banco (Admin cadastra e altera; Operador acrescenta "+ Nova rádio"); configuração da empresa no banco (modelo da mensagem com campos e trechos opcionais, nome falado, telefone, limite de rejeição, fuso UTM, antecedência) usada pelo tradutor e pelas travas; mensagem da rádio pelo modelo (nucleo/mensagem.py, sem sufixo de distrito, {codigo} preenchido depois de gravar); sugestão de rádio por comunidade com o distrito + "Sem rádio cadastrada para"; envio com valor gravado, cobrança fechada ou por minuto, custo antigo opcional, economia calculada/informada e tempo de ar economizado (nucleo/economia.py); PDF do roteiro gerado no servidor (fpdf2) e MP3 (Piper) anexos no e-mail (SMTP por variáveis; Mailpit local v1.31.3 conferido pelo SHA-256), guardados cifrados (AES-256-GCM, cofre.py) e baixáveis pelo histórico; link "Confirmar recebimento" (token de uso único, 7 dias, GET só mostra, POST confirma, origem conferida); WhatsApp (wa.me) e cópia registrados; limite de e-mails por hora; texto com número longo/e-mail/site recusado; FAROL_EMAIL=0 desliga o e-mail; painel e comparativo usam o tempo da mensagem.
- Dependências novas (PyPI, OSV sem vulnerabilidade aberta em 14/10/2026): fpdf2 2.8.9 (LGPL-3.0), cryptography 50.0.2 (Apache-2.0/BSD), fonttools 4.66.1 (MIT), pillow 12.3.0 (MIT-CMU).
- Testes: rodar_testes.ps1 20 de 20 (teste_radio 72/72 com o Mailpit; navegador 92/92; matriz com as rotas novas); --so-algoritmo igual ao passo 12.

### Fase D (14/10/2026)
- Feito: prazo do aviso (nucleo/prazo.py: 72 h ou 5 dias úteis com equipamento vital, até o primeiro envio à rádio); relatório do período (nucleo/relatorio.py: resumo, por tipo, por rádio, comunidades mais afetadas, fora do prazo, sem envio, como a economia foi calculada, lista detalhada, comparação com o mês anterior; filtros município, tipo, rádio e pessoa); comprovante do aviso; relatório de auditoria (Admin da empresa) e auditoria geral de acessos (Admin do Farol, filtro por empresa); PDF (apresentacao/pdf_relatorio.py) e CSV protegido contra fórmula, cada exportação na auditoria com quem gerou e o código FRL do relatório; painel do mês no dashboard; semente de demonstração (comunidades.semente_demo: 16 avisos, ~19 envios e 4 rádios fictícios, uma vez só); telas: aba Relatórios, comprovante no histórico, exportação da auditoria.
- Testes: rodar_testes.ps1 21 de 21 (teste_relatorios 44/44; navegador 97/97; matriz com 46 rotas fechadas); --so-algoritmo igual ao passo 12.

### Fase E (14/10/2026)
- Feito: menu por perfil conforme a matriz (Admin do Farol: Empresas e Auditoria geral; Admin da empresa: Novo aviso, Histórico, Relatórios, Usuários, Rádios, Configurações, Auditoria; Operador: Novo aviso, Histórico, Relatórios; Consulta: Mapa, Histórico, Relatórios; Relatórios com Painel do mês, Do período e Comparativo); telas de admin ligadas à API real: usuários com municípios (convite sem senha, senha temporária, último admin protegido), rádios (alcance por município e por comunidade com distrito, editar, desativar), configurações (modelo da mensagem com prévia, telefone, limite, fuso UTM, antecedência), empresas com CNPJ alfanumérico opcional (validação do protótipo do Lucas portada para Python) e suspender/reativar (sessões encerradas); visual único Farol (Âmbar, Noite, Maré, Névoa) em todas as telas, inclusive entrar e trocar a senha, tema claro e escuro (o fundo do mapa acompanha); botão Ajuda por perfil e "?" para UC, equipamento vital, corrigida, rejeitada, limite de rejeição, localidade vizinha, código de verificação e economia.
- Testes: rodar_testes.ps1 21 de 21 (acesso 46/46 com CNPJ, municípios e suspensão; matriz com PATCH /api/empresas; navegador 107/107 com rádios, configurações, ajuda, dicas, tema escuro e 44 px nas telas do Admin); --so-algoritmo igual ao passo 12.

### Fase F (14/10/2026, parcial)
- Feito: filtro do mapa por estado e município ("Ir para", aproxima no município) e agrupamento das UCs por circuito e por transformador na conferência (nucleo/agrupamento.py; só códigos da rede e contagens).
- Não feito (vai para "Próximos passos" no README): selecionar um polígono pronto (comunidade ou distrito) para simular o desligamento e aceitar UTM/GMS na tela de simulação. As duas ficam no mapa estático de demonstração (mapa_template.html), que tem testes de tela idênticos ao passo 12; mexer nele agora arriscaria a referência às vésperas da apresentação. Colorir os pontos por circuito no mapa também fica para depois.
- Testes: rodar_testes.ps1 21 de 21 (travas 49/49, API 77/77, navegador 108/108); --so-algoritmo igual ao passo 12.

### Fase G (14/10/2026)
- Feito: README completo (o que é, resultados do pipeline, passo a passo no Windows, perfis, arquitetura MVC, segurança/LGPD, validação, próximos passos); SEGURANCA.md com a tabela "Ameaça → proteção → teste que prova"; ORIGEM.md na raiz (dados, componentes, voz, Mailpit, dependências, licenças e hashes); docs/DEMO.md (roteiro de 5 minutos com o bloqueio do equipamento vital); DEPLOY.md com as variáveis novas; testes/rodar_testes.ps1 (desde a Fase B). Banco local migrado e com a semente de demonstração (16 avisos, 19 envios, 4 rádios; auditoria íntegra).
- Bateria final: rodar_testes.ps1 21 de 21 (980 verificações); --so-algoritmo igual ao passo 12.
- PR: sabrina/plano-final -> melhorias (link no fim da sessão).

## Decisões da Fase H (tomadas sem perguntar: a opção mais segura e mais simples)
- Atribuição: tudo conta no mês em que o aviso foi criado (envios, custo e prazo do aviso vão para o mês dele).
- Auditoria geral de acessos (Admin do Farol) não tem "Enviar": o Admin do Farol não tem domínio de empresa para restringir os destinatários.
- Equipamento vital por comunidade não é guardado (só a contagem por município): os relatórios mostram o vital por município.
- Não existe campo de justificativa de atraso: a coluna aparece com "—" até a distribuidora pedir esse campo.
- Ficha da comunidade, mapa de calor, linha do tempo, lista de vias e comprovante na tela só mostram: não vão para a auditoria. Todo relatório na tela vai, como "gerou relatório X (tela)"; todo PDF, CSV, via e envio também.
- Projeção do ano: acumulado + média dos meses fechados (contando meses fechados sem gasto como zero) x meses que faltam; o mês em andamento não entra na média. Sem mês fechado (janeiro), sem projeção.
- Setas ↑ ↓ no PDF viram + e - (as fontes do PDF são Latin-1); na tela e no CSV ficam as setas.
- A segunda via usa a mesma chave do cofre dos arquivos (FAROL_CHAVE_ARQUIVOS); sem a chave o PDF não é gerado (503), para nunca existir relatório sem via.
- Envio de relatório: 1 a 5 destinatários do domínio da empresa, 10 envios por hora por usuário (na memória do processo, como o limite de login).
- Confirmação de recebimento pela rádio (link do e-mail) fica na auditoria sem usuário: quem confirma é a rádio, não alguém do Farol.
- Alerta de repetição (padrão: 3 desligamentos em 30 dias, configurável): amarelo, não bloqueia; aparece na conferência e, ao gerar, vai para a auditoria.
- Registro total (H6) é conferido lendo o código das rotas (teste_registro_total.py) e, no banco, pelo teste_relatorios_h (nenhuma linha com usuário sem nome e perfil).
- Envio de aviso cancelado continua no gasto, nos pedidos e no tempo no ar (a rádio foi paga); o aviso cancelado não conta como desligamento nem entra no prazo.
- Semente do ano separada da semente de demonstração (semear_ano, marca "semente de demonstração (ano)"): os testes que contam a semente de demonstração não mudam; o comando da semente_demo roda as duas.
- O banco ganha as colunas e a tabela da Fase H pela semente (como nas fases anteriores), não na subida da API: no deploy, rodar a semente de novo (DEPLOY.md).
- Na tela, o relatório mensal antigo (por tipo, por rádio, lista) deu lugar ao documento da Fase H, o mesmo do PDF e do CSV; o JSON da API mantém os campos antigos para quem já os usa (painel do mês).
- Os testes que leem o texto dos PDFs passam a ler o fluxo até o "endstream" com zlib tolerante: antes, um \r no fim dos dados comprimidos (acaso do conteúdo) fazia o teste falhar de vez em quando.
- Bateria final da Fase H: rodar_testes.ps1 com 23 de 23 testes OK (Relatórios completos 69/69, Registro total 5/5, Tela do app 109/109, minimização 0 nas duas cidades); --so-algoritmo igual ao passo 12 (835 cenários, cobertura 88.3%, precisão 95.0%, aviso 44s -> 14s).
- Na tela, a coluna do painel ficou presa à largura dele (minmax(0, 1fr)); o teste da tela confere que nada passa da largura do painel.
