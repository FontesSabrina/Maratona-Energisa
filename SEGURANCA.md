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

Nenhum dado de cliente real da distribuidora foi usado.

## O que o protótipo protege hoje

**Minimização de dados no mapa (HTML).** O arquivo `saida/mapa_comunidades.html` não leva nome de titular, número de UC nem endereço. O clique num ponto mostra só a classe da unidade, a localidade digitada no cadastro, a comunidade identificada, a comunidade real (só para validação), a origem da coordenada e o transformador.

**Minimização de dados no PDF para a rádio.** O roteiro traz só nomes de comunidades e contagens de unidades.

**Exceção: o aviso de hoje.** O texto do aviso atual ("fazenda a fazenda") lista nomes de imóveis e ruas, porque reproduz o comunicado público que já vai ao ar no rádio. Ele nunca inclui nomes de pessoas, números de UC nem coordenadas.

**Sem servidor.** O mapa é um único arquivo HTML que abre direto no navegador. Não há banco de dados, login nem servidor do projeto que possa ser invadido ou vazar dados.

**Conexões travadas.** O HTML tem uma política de segurança de conteúdo (Content Security Policy) que:
- só deixa rodar os scripts que vieram dentro do arquivo, conferidos pelo código SHA-256 de cada um. Um script colado depois no arquivo não roda;
- só carrega imagens dos servidores de fundo de mapa da Esri (`server.arcgisonline.com`), além de imagens e fontes embutidas no próprio arquivo;
- bloqueia qualquer outra conexão: envio de dados, fontes externas, formulários e outras páginas dentro da página.

**Biblioteca e fontes embutidas e conferidas.** A biblioteca de mapas (Leaflet 1.9.4) e as fontes IBM Plex Sans e IBM Plex Mono (licença SIL OFL 1.1) vêm embutidas no HTML, e não de uma CDN ou de um servidor de fontes. Foram copiadas dos pacotes oficiais, e o código de integridade de cada pacote foi conferido com o publicado pelo registro npm (ver `ORIGEM.md` em `src/comunidades/apresentacao/vendor/leaflet/` e em `vendor/ibm-plex/`). O git guarda esses arquivos sem converter o fim de linha (`.gitattributes`), para o SHA-256 de cada um continuar igual ao do pacote. Sem internet, o mapa funciona normalmente, só sem a imagem de fundo.

**Código de verificação no PDF.** O rodapé do roteiro traz um código SHA-256 calculado no navegador. Qualquer alteração no texto gera um código diferente.

- O código é calculado sobre este texto, em UTF-8, com as linhas separadas por quebra de linha simples:
  ```
  texto=<aviso completo, como impresso>
  data=<dd/mm/aaaa>
  horario=<ex.: 8h às 14h>
  chave=<código da chave>
  gerado=<dd/mm/aaaa hh:mm>
  ```
- Para conferir, basta recalcular. Em Python: `hashlib.sha256(entrada.encode("utf-8")).hexdigest()`.
- **Limite:** o código detecta alteração no texto em relação ao que foi gerado, mas **não é assinatura digital**. Quem altera o texto pode calcular um código novo. Para servir de prova, o código precisa ficar registrado num sistema da distribuidora no momento da geração (ver abaixo).

**Sem segredos no código.** Não há senha, token nem chave de acesso no código nem no histórico do git.

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
