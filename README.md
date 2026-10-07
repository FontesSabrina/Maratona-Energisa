# Desafio 3: Fazenda por fazenda, ou uma comunidade só?

Identifica automaticamente as **comunidades afetadas por um desligamento programado**, para que o aviso no rádio cite "Braúna, Graminha e parte de Tomé Nogueira" em vez de listar sítio por sítio.

Cenário de teste: **Leopoldina/MG** (município inteiro), com dados reais do Censo IBGE 2022. A parte da distribuidora (rede elétrica, transformadores e clientes) é **fictícia**, gerada sobre as casas reais.

## Resultados

| Métrica | Só o cadastro digitado | Algoritmo |
|---|---|---|
| Comunidade correta por UC, zona rural | 56,1% | **90,9%** |
| Comunidade correta por UC, zona urbana | 85,2% | **95,6%** |
| Comunidades atingidas que entram no aviso (835 cenários) | – | **93,2%** |
| Duração média do aviso no rádio | 44 s | **14 s** |

Exemplo, chave CF-0066 (758 UCs rurais): o aviso cai de 358 palavras (~143 s) para ~21 s, com 100% das comunidades atingidas citadas.

## Só quero ver funcionando

O mapa já vem pronto no repositório: abra `saida/mapa_comunidades.html` no navegador (precisa de internet para o fundo do mapa). Para abrir já simulando uma chave, use `saida/mapa_comunidades.html#CF-0066`.

## Como rodar o projeto

**Pré-requisitos:** [Git](https://git-scm.com/downloads) e [uv](https://docs.astral.sh/uv/). Não é preciso instalar Python, porque o uv baixa a versão certa sozinho.

```powershell
# Windows (PowerShell): instalar o uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
```bash
# Linux / macOS: instalar o uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Feche e abra o terminal depois de instalar. Em seguida:

```bash
git clone <URL-DO-REPOSITORIO>
cd <pasta-do-repositorio>
uv sync                                # cria o ambiente e instala as dependências
uv run comunidades                     # pipeline completo
```

- **Primeira execução:** ~5 a 8 min, porque baixa ~110 MB do IBGE e as vias do OpenStreetMap para `data/raw/`.
- **Execuções seguintes:** ~3 min.
- `uv run comunidades --so-algoritmo` reaproveita a rede e os clientes já gerados e roda só o algoritmo, a avaliação e o mapa. É o modo útil para quem estiver mexendo no algoritmo.

Ao final, o terminal mostra as métricas, e o mapa é regravado em `saida/mapa_comunidades.html`.

> As vias vêm do OpenStreetMap, que é atualizado continuamente. Quem baixar em outro dia pode obter uma rede fictícia um pouco diferente e números levemente diferentes.

## Onde mexer para propor melhorias

| Quero mudar... | Arquivo |
|---|---|
| Como o algoritmo decide a comunidade (vizinhos, raio, pesos) | `algoritmo.py`, constantes no topo |
| O texto do aviso de rádio e a regra "inteira/parte" | `desligamento.py` |
| Abreviações e prefixos reconhecidos no cadastro | `nomes.py` |
| Tipos e proporções de erro no cadastro fictício | `clientes.py` |
| Tamanho dos transformadores, alimentadores e chaves | `rede.py` |
| Visual e comportamento do mapa | `mapa_template.html` |

## Camadas

| Camada | Origem | Fonte |
|---|---|---|
| Limite municipal, distritos, setores censitários | Real | IBGE, Malha de Setores 2022 |
| Localidades oficiais (15) | Real | IBGE, Localidades 2022 |
| Endereços (30.955, sendo 5.553 rurais) | Real | IBGE, CNEFE 2022 |
| **Gabarito**: comunidade de cada endereço | Real | CNEFE `DSC_LOCALIDADE`, limpo (65 comunidades rurais e 47 bairros) |
| Vias | Real | OpenStreetMap |
| Subestação, 9 alimentadores, 835 chaves, 2.160 transformadores | Fictícia | Gerada pelas vias reais (`rede.py`) |
| 29.865 UCs com titular, imóvel e localidade digitada com ruído | Fictícia | `clientes.py` |

Ruído simulado no cadastro rural: 22% de localidade vazia, 18% abreviada, 10% com o nome do sítio no lugar da comunidade, 8% com erro de digitação, 5% com a comunidade vizinha, 18% sem coordenada e 4% com coordenada errada.

## Algoritmo (`algoritmo.py`)

Usa **apenas** o que uma distribuidora tem: o cadastro de UCs e a posição dos transformadores. O gabarito do IBGE é lido só em `avaliacao.py`.

1. **Coordenadas**: se a coordenada está ausente ou fica a mais de 600 m do próprio transformador, usa a posição do trafo.
2. **Texto**: normaliza ("COR. STA CRUZ" → "CORREGO SANTA CRUZ"), remove prefixos ("COMUNIDADE", "PROX.") e descarta campos vazios e nomes de sítio ou fazenda.
3. **Vocabulário**: agrupa variantes e erros de digitação num nome canônico (fuzzy matching).
4. **Votação espacial**: cada UC recebe o nome predominante entre as 15 vizinhas mais próximas, num raio de até 1,5 km e com peso pela distância. Vizinhas no mesmo transformador valem 4 vezes mais. Isso corrige localidades vazias, desatualizadas ou com o nome do sítio.
5. **Homônimos**: o mesmo nome em distritos diferentes vira comunidades distintas, por exemplo "Tomé Nogueira (Tebas)".
6. **Desligamento** (`desligamento.py`): agrupa as UCs a jusante da chave por comunidade. Se ≥ 90% das UCs da comunidade forem afetadas, ela entra no aviso inteira; caso contrário, como "parte de".

## Estrutura

```
src/comunidades/
  ibge.py          camadas reais + gabarito
  osm.py           malha viária
  rede.py          rede elétrica fictícia
  clientes.py      cadastro fictício de UCs com ruído
  nomes.py         normalização e grafia dos nomes
  algoritmo.py     identificação das comunidades
  desligamento.py  simulação e texto do aviso
  avaliacao.py     comparação com o gabarito
  mapa.py          gera o HTML interativo (+ mapa_template.html)
saida/             mapa, comunidades.gpkg, ucs_comunidade.gpkg, avaliacao_cenarios.csv
```

## Limitações conhecidas

- O erro restante se concentra nas **fronteiras entre comunidades vizinhas**, onde até o gabarito é incerto, e em UCs cuja localidade digitada é a da comunidade vizinha (51% de acerto nesse caso).
- A rede elétrica é fictícia: o traçado segue as vias reais, mas não representa a rede real da distribuidora.
- O gabarito tem pequenas inconsistências de grafia, como "Jardim Caicara" e "Jardim Caicaras". Elas contam como erro na avaliação.
- Nenhum dado pessoal real é usado: os titulares são fictícios, e o campo do CNEFE que às vezes traz nomes de pessoas foi descartado.

## Fontes

- CNEFE 2022: `ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/31_MG/3138401_LEOPOLDINA.zip`
- Localidades 2022: `geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/`
- Setores 2022: `geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/setores/shp/UF/MG_setores_CD2022.zip`
- Vias: OpenStreetMap (via OSMnx)
