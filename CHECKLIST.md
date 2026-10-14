# Checklist do plano final (docs/PLANO_FINAL.md)

Branch: sabrina/plano-final (a partir da sabrina/passo15-tradutor, commit ee9b030).
Uma sessão nova continua daqui: ler docs/PLANO_FINAL.md e a última fase sem [x].

- [x] Passo 0: plano salvo em docs/PLANO_FINAL.md e este checklist criados
- [x] Fase A: terminar o Passo 15 (tela de conferência, planilhas demo)
- [x] Fase B: tipo de desligamento e auditoria encadeada por hash
- [ ] Fase C: rádios, modelo de mensagem, envio por e-mail, confirmação, arquivos criptografados
- [ ] Fase D: comprovante, relatório mensal, relatórios de auditoria, painel do mês, semente de demonstração
- [ ] Fase E: telas por perfil, visual único Farol, Ajuda
- [ ] Fase F: só se sobrar tempo (filtros do mapa, polígono pronto, UTM/GMS na simulação, transformador/circuito)
- [ ] Fase G: README, SEGURANCA.md, ORIGEM.md, docs/DEMO.md, testes/rodar_testes.ps1, PR para a melhorias

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
