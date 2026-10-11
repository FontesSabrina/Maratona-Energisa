# Segurança e proteção de dados

Este documento explica, em linguagem simples, como o protótipo trata segurança e dados pessoais, e o que mudaria numa implantação real na distribuidora.

## De onde vêm os dados

| Dado | Origem | Pessoal? |
|---|---|---|
| Limites do município, distritos, setores e localidades | IBGE, Censo 2022 (público) | Não |
| Endereços (posição e tipo de imóvel) | CNEFE do IBGE (público) | Não identifica pessoas |
| Vias | OpenStreetMap (público) | Não |
| Rede elétrica (subestação, alimentadores, chaves, transformadores) | **Fictícia**, gerada pelo projeto | Não |
| Clientes (titular, número da UC, campo de localidade) | **Fictícios**, gerados pelo projeto | Inventados |
| Planilha de UCs afetadas (UC e coordenada), entrada do app em construção | Distribuidora (hoje, planilhas de teste geradas da rede fictícia) | **Sim**, quando for real |

Nenhum dado de cliente real da distribuidora foi usado até agora.

## O que muda com a planilha, a API e o banco (em construção)

Desde 11/10/2026 o Farol está passando de um HTML de demonstração para um app com API em Python e banco Postgres. A entrada passa a ser a planilha que a distribuidora envia, com as UCs afetadas e suas coordenadas. Uma UC com coordenada identifica uma casa, então a planilha é tratada como dado pessoal desde já, mesmo nos testes:

- **A planilha não é guardada.** A API lê o arquivo em memória, calcula os municípios, as comunidades e o aviso e descarta o arquivo. O banco guarda só o resultado agregado: municípios, comunidades, contagens e o texto do aviso. Nunca número de UC nem coordenada.
- **A tela não mostra UCs.** O relatório de validação aponta problemas pelo número da linha da planilha (sem coordenada, fora da área de concessão, UC repetida), sem repetir a UC.
- **Login e perfis.** Toda rota da API, menos a de saúde e a de entrar, exige uma sessão, e a permissão de cada perfil é conferida no servidor, não só escondida na tela. Os perfis são Admin do Farol, Admin da empresa, Operador e Consulta. Cada empresa só vê os próprios usuários, avisos e registro. O teste `testes/api/teste_acesso.py` confere a matriz inteira.
- **Senhas.** O banco guarda só o hash Argon2id. A senha nova tem pelo menos 12 caracteres e não pode conter o e-mail. Senha errada e e-mail desconhecido dão a mesma resposta, no mesmo tempo. Cinco erros seguidos bloqueiam a conta por 15 minutos, e cada endereço IP tem um limite de tentativas. Toda senha inicial é temporária e aleatória, aparece uma única vez e tem de ser trocada no primeiro acesso. Nenhuma senha fica no código ou no git: os 4 usuários iniciais são criados pela semente (`comunidades.semente`), que gera as senhas na hora.
- **Sessões.** O token vai num cookie que o JavaScript não lê (HttpOnly), só vai para o próprio site (SameSite=Strict) e, em produção, só por HTTPS (Secure). O banco guarda só o hash do token. A sessão acaba depois de 8 horas sem uso ou 24 horas no total, ao sair, ao trocar a senha (as outras sessões) e quando o usuário é bloqueado. Requisições que mudam dados vindas de outra origem são recusadas.
- **Áudio sem sair do servidor.** O MP3 do aviso é gerado no próprio servidor (voz Piper, offline): o texto não vai para nenhum serviço de voz de fora, e não há chave para guardar. O navegador toca o áudio da memória da página (CSP `media-src 'self' blob:`). O registro anota só que o áudio foi gerado, o município e a duração, nunca o texto. Licenças: o Piper é GPL-3.0 (sem obrigação enquanto roda só no nosso servidor; se o Farol for distribuído, o jurídico avalia), o LAME do MP3 é LGPL e as vozes vêm de dados de treino CC0.
- **Computador compartilhado.** Ao sair, a tela apaga tudo do usuário anterior (resultados, listas e o roteiro), e não só esconde.
- **Registro de atividades.** Entradas, senhas erradas, bloqueios, cadastros, avisos gerados e textos finais ficam registrados com quem e quando, sem nenhum dado de cliente.
- **Ainda falta antes de dado real:** segundo fator de autenticação (MFA) para os admins, recuperação de senha por e-mail e uma revisão de segurança independente.
- **Conexões.** O app só fala com a própria API (CSP `connect-src 'self'`) e com os fundos de mapa da Esri. O mapa de demonstração continua sem nenhuma conexão.
- **Tela sem nada embutido.** A tela (`apresentacao/app/`) carrega o script, o estilo, o Leaflet e as fontes do próprio servidor. A CSP vem no cabeçalho de toda resposta da API: `script-src 'self'` e `style-src 'self'`, sem `unsafe-inline`, mais `frame-ancestors 'none'`. Só a documentação interativa (`/api/docs`, para desenvolvimento) fica fora, porque carrega o Swagger de fora. Todo texto vindo da API ou da planilha entra na tela como texto, nunca como HTML. O teste `testes/navegador/teste_app.mjs` confere que nenhuma UC nem coordenada da planilha aparece no HTML da página ou no PDF.
- **O dashboard só agrega o histórico.** A rota `/api/painel` (perfis que veem o histórico, só a própria empresa) devolve contagens: avisos, UCs, comunidades, municípios, avisos por mês, os municípios e as comunidades que mais aparecem e os próximos desligamentos. Nada de UC, coordenada ou texto de aviso. O teste `testes/api/teste_api.py` confere os campos, e o `teste_acesso.py`, as permissões e o isolamento entre empresas.
- **Os pontos das UCs são temporários.** Desde 11/10/2026, para quem enviou a planilha conferir o resultado, a resposta do envio traz um ponto por UC: só latitude, longitude (5 casas, cerca de 1 m) e a comunidade, nunca o número da UC. Os pontos ficam só na memória do navegador e são desenhados num canvas (não entram no HTML). Não vão para o banco, o histórico, o PDF nem o áudio, e somem ao abrir um aviso do histórico, ao trocar de planilha ou ao sair. O perfil Consulta, que só vê o histórico, nunca os vê. A dica de cada ponto mostra só a comunidade. Os testes conferem isso: `testes/api/teste_api.py` (coordenadas só nos pontos e nunca no histórico) e `testes/navegador/teste_app.mjs`. Fora isso, o mapa desenha os contornos públicos dos municípios e de todas as comunidades dos municípios afetados, que vêm do IBGE.
- **Segredos fora do código.** A senha do banco fica só na variável de ambiente `DATABASE_URL`, num arquivo `.env` que o git ignora. Antes de publicar: usuário próprio do app no banco (não o superusuário `postgres`) e senha forte.

## O que o protótipo protege hoje

**Minimização de dados no mapa (HTML).** O arquivo `saida/mapa_comunidades.html` não leva nome de titular, número de UC nem endereço. O clique num ponto mostra só a classe da unidade, a localidade digitada no cadastro (quando ela é nome de imóvel, pelo mesmo critério que já a descarta na votação, aparece "(nome de imóvel)", e o texto não vai para o HTML), a comunidade identificada, a comunidade real (só para validação), a origem da coordenada e o transformador. A varredura `py -m uv run python -m comunidades.validacao.minimizacao` confere isso: procura no HTML gerado cada titular, número de UC, nome de imóvel e logradouro do cadastro.

**Minimização de dados no PDF para a rádio.** O roteiro traz só nomes de comunidades e contagens de unidades.

**Exceção: o aviso de hoje.** O texto do aviso atual ("fazenda a fazenda") lista nomes de imóveis e ruas, porque reproduz o comunicado público que já vai ao ar no rádio. Ele nunca inclui nomes de pessoas, números de UC nem coordenadas.

**Sem servidor.** O mapa é um único arquivo HTML que abre direto no navegador. Não há banco de dados, login nem servidor do projeto que possa ser invadido ou vazar dados.

**Conexões travadas.** O HTML tem uma política de segurança de conteúdo (Content Security Policy) que:
- só deixa rodar os scripts que vieram dentro do arquivo, conferidos pelo código SHA-256 de cada um. Um script colado depois no arquivo não roda;
- só carrega imagens dos servidores de fundo de mapa da Esri (`server.arcgisonline.com`), além de imagens e fontes embutidas no próprio arquivo;
- bloqueia qualquer outra conexão: envio de dados, fontes externas, formulários e outras páginas dentro da página.

**Biblioteca e fontes embutidas e conferidas.** A biblioteca de mapas (Leaflet 1.9.4) e as fontes IBM Plex Sans e IBM Plex Mono (licença SIL OFL 1.1) vêm embutidas no HTML, e não de uma CDN ou de um servidor de fontes. Foram copiadas dos pacotes oficiais, e o código de integridade de cada pacote foi conferido com o publicado pelo registro npm (ver `ORIGEM.md` em `src/comunidades/apresentacao/vendor/leaflet/` e em `vendor/ibm-plex/`). O git guarda esses arquivos sem converter o fim de linha (`.gitattributes`), para o SHA-256 de cada um continuar igual ao do pacote. Sem internet, o mapa funciona normalmente, só sem a imagem de fundo.

**Contorno importado tratado como dado.** No desligamento por área, o arquivo (.kml, .geojson ou .json, até 5 MB e 20.000 vértices) é lido só no navegador, sem ir para nenhum servidor. Dele saem apenas as coordenadas dos polígonos: nomes, descrições e propriedades são descartados, e nenhum texto do arquivo entra na página como HTML (um KML pode trazer HTML e scripts nas descrições). O nome do arquivo aparece só como texto. A CSP continua a mesma, e o botão "Baixar área (GeoJSON)" funciona sem nenhuma exceção nova. Para a área, o HTML leva por UC só dois códigos a mais (distrito e atividade), nunca nome, número de UC ou endereço.

**Contorno da concessão tratado como dado.** A página de entrada desenha a área de concessão a partir de `distribuidoras/concessao/EMG.kml`. O Python (`fontes/concessao.py`) lê do KML só as coordenadas dos polígonos e descarta nomes, descrições e propriedades. As malhas das UFs e dos municípios vêm da API pública do IBGE na geração da página, e nunca do navegador. No HTML vão só a geometria simplificada, o nome e o código IBGE dos municípios e, dos já processados, o link do mapa e as contagens do resumo. A entrada tem a mesma CSP do mapa: scripts só pelo hash, `connect-src 'none'` e só os fundos da Esri de fora. Todo nome vindo dos dados entra na tela como texto, nunca como HTML.

**Tamanho do aviso de hoje no modo área.** Para comparar o aviso de hoje com o do Farol numa área, o HTML leva por UC só um código numérico do local que o aviso de hoje citaria (o imóvel, senão a rua) e, para cada código, o número de palavras do nome desse local. Os nomes não vão para o HTML, e os códigos seguem a ordem em que os locais aparecem no cadastro, não a alfabética, então nem o código nem a contagem de palavras permitem reconstruir um imóvel ou uma rua. Risco que fica: o código mostra quais UCs estão no mesmo imóvel ou na mesma rua (um agrupamento sem nome), parecido com o que o transformador de cada UC já mostra; como a rede e os clientes são fictícios, aceitamos esse risco no protótipo.

**Código de verificação no PDF.** O rodapé do roteiro traz um código SHA-256 calculado no navegador. Qualquer alteração no texto gera um código diferente.

- O código é calculado sobre este texto, em UTF-8, com as linhas separadas por quebra de linha simples:
  ```
  texto=<aviso completo, como impresso>
  data=<dd/mm/aaaa>
  horario=<ex.: 8h às 14h>
  chave=<código da chave>
  gerado=<dd/mm/aaaa hh:mm>
  ```
- Com o aviso em inglês ou espanhol, o `texto` entra no idioma escolhido, mas `data`, `horario` e `gerado` continuam nos formatos acima (dd/mm/aaaa, "8h às 14h" e dd/mm/aaaa hh:mm).
- No desligamento por área, a linha `chave=` dá lugar a:
  ```
  area=<desenhada ou importada>;poligonos=<n>;vertices=<n>;sha256=<SHA-256 da forma canônica do contorno>
  ```
  A forma canônica é o texto `lon,lat` de cada vértice com 6 casas decimais, com `;` entre vértices, `|` entre anéis e `/` entre polígonos (cada anel fechado, como no GeoJSON). Quem tem o GeoJSON baixado pelo botão "Baixar área (GeoJSON)" recalcula esse código (ver `forma_canonica` em `src/comunidades/nucleo/area.py`). O número do aviso passa a ser `AV-<aaaammdd>-AREA-<8 primeiros caracteres desse código>`.
- Para conferir, basta recalcular. Em Python: `hashlib.sha256(entrada.encode("utf-8")).hexdigest()`.
- **Limite:** o código detecta alteração no texto em relação ao que foi gerado, mas **não é assinatura digital**. Quem altera o texto pode calcular um código novo. Para servir de prova, o código precisa ficar registrado num sistema da distribuidora no momento da geração (ver abaixo).

**Sem segredos no código.** Não há senha, token nem chave de acesso no código nem no histórico do git.

## Área administrativa — protótipo

A página `saida/admin.html` (link "Área administrativa (protótipo)" na página de entrada) mostra como seria o cadastro das empresas que usam o Farol e dos usuários de cada empresa. **Ela não é um controle de acesso real.** É uma demonstração navegável:

- **Entrada simulada.** "Entrar como" (Admin do Farol, Admin da empresa, Operador ou Consulta) não pede senha e não protege nada. Quem abre o arquivo pode escolher qualquer perfil. As permissões por perfil existem só para mostrar o comportamento esperado.
- **Tudo na memória do navegador.** Nada é gravado: nem em servidor, nem em `localStorage` ou `sessionStorage`. Recarregar a página volta aos dados de demonstração.
- **Dados fictícios.** Duas empresas ("Distribuidora Demonstração MG" e "Cooperativa Rural Exemplo") e cinco usuários com nomes de exemplo, e-mails em subdomínios de `example.com` (reservado para exemplos) e CNPJs alfanuméricos de teste, válidos no cálculo dos dígitos mas sem empresa real. Os municípios e códigos IBGE são reais.
- **Mesmas travas do mapa.** CSP com os scripts só por hash, `connect-src 'none'` e nenhum servidor externo (nem os fundos de mapa). Todo texto digitado é exibido como texto (nunca como HTML): um nome de empresa como `<img src=x onerror=...>` aparece escrito, sem rodar nada. O teste `testes/navegador/teste_admin.mjs` confere isso, a falta de requisições de rede e de erros no console.
- **Minimização (LGPD).** O cadastro de usuário pede só o necessário para dar acesso: nome, e-mail corporativo (do domínio permitido da empresa), cargo ou setor (opcional), perfil e municípios. **Não há campo de CPF, data de nascimento, endereço nem telefone pessoal.** Da empresa, além dos dados cadastrais, só o gestor do contrato e o encarregado de dados (DPO), exigido pela LGPD (art. 41).
- **Convite sem senha.** "Convidar usuário" não cria senha: a tela explica que, na produção, a pessoa recebe um link e cria a própria senha.
- **Arquivo de configuração.** O botão "Gerar arquivo de configuração (.toml)" gera o arquivo no formato de `distribuidoras/*.toml`, que o pipeline carrega. Ele nunca leva usuários nem e-mails (o teste confere com o `distribuidora.py`).
- **Registro de atividades** só da sessão, na memória, com opção de baixar em texto.

**Como seria em produção:**

- **No servidor da distribuidora**, com o cadastro num banco de dados dela, e não num arquivo aberto no navegador. Cada regra de permissão é conferida no servidor, a cada pedido.
- **Login corporativo** (SSO com OpenID Connect, por exemplo o Microsoft Entra ID da empresa) e **verificação em 2 etapas** obrigatória para administradores.
- **Senhas, quando houver, só como hash Argon2id.** O convite é um link de uso único, com prazo, e a pessoa cria a própria senha.
- **Isolamento por empresa** garantido no servidor e no banco: o admin de uma empresa nunca lê nem altera dados de outra, nem por acesso direto ao endereço.
- **Auditoria imutável:** quem fez o quê, quando e em qual registro, guardado num registro que não pode ser apagado nem alterado.
- **LGPD:** minimização (os campos acima), encarregado de dados indicado por empresa, base legal (execução do contrato com a distribuidora e cumprimento da obrigação regulatória de aviso), prazo de guarda dos dados de quem deixa de ser usuário e atendimento aos direitos do titular.

## O que a implantação real exigiria

O protótipo usa dados públicos e fictícios. Com o cadastro real da distribuidora, seria preciso:

- **Dados que nunca saem da empresa.** O cadastro de clientes fica na infraestrutura da distribuidora. O processamento roda lá dentro, e para fora só saem os produtos finais: o texto do aviso, o roteiro e contagens por comunidade.
- **Cadastro criptografado.** Banco de dados criptografado em disco e conexões criptografadas entre os sistemas internos.
- **Controle de acesso.** Login com a conta corporativa, e cada perfil vê só o necessário. O operador que gera o aviso não precisa ver o titular de cada UC.
- **Registro de quem gerou cada aviso.** Usuário, data e hora, chave, texto e código de verificação ficam guardados num registro que não pode ser apagado nem alterado. Assim o código do PDF passa a valer como prova.
- **Mapa compartilhável sem posição de cliente.** Um mapa que pode ser enviado a outras pessoas não deve levar a posição de cada cliente. Em produção, os pontos seriam mostrados agrupados por transformador (por exemplo, "Transformador TR-11154: 12 unidades"). A posição individual ficaria só nos sistemas internos da distribuidora, com acesso controlado.
- **Clientes com equipamento vital.** Esse cadastro é dado sensível de saúde. No aviso e no mapa ele apareceria só como contagem, nunca com nome ou endereço.

## Relação com a LGPD

- **Finalidade.** O dado do cliente é usado para avisar quem vai ficar sem energia, o que a regulação do setor elétrico exige (REN ANEEL 1.000/2021). Essa obrigação é a base legal do tratamento.
- **Necessidade e minimização.** O produto final (o aviso no rádio) cita comunidades, não pessoas. Nem o mapa nem o PDF carregam dado pessoal.
- **Dados sensíveis.** Informação de saúde (equipamento vital) só aparece como contagem.
- **Segurança.** Sem servidor, conexões travadas e, na implantação real, criptografia, controle de acesso e registro de uso.
- **Transparência.** Toda tela e todo documento dizem que a rede e os clientes são fictícios e que os dados territoriais são reais.

## Histórico do git

Os commits de `129a9f8` a `20514ae` (os seis primeiros do repositório) contêm uma versão do mapa HTML com **nomes fictícios de titulares**, números de UC inventados e o imóvel ou rua de cada unidade. Esses nomes foram sorteados pelo próprio projeto a partir de listas de nomes comuns e não pertencem a clientes reais. Por isso o histórico **não foi reescrito**: a correção vale do commit seguinte em diante. Com dados reais, o histórico teria de ser reescrito e as cópias publicadas, apagadas.
