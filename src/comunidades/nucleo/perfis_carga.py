"""Hipóteses de demonstração, a validar com a distribuidora e por região.

Perfis de sensibilidade de cada atividade ao longo do dia: quanto pesa deixar uma UC
sem luz em cada meia hora, por tipo de dia. Usados só para sugerir a janela de menor
dano do desligamento; a equipe continua decidindo. Nada aqui é dado medido.
"""

from dataclasses import dataclass

# Níveis de sensibilidade (inteiros, para o navegador e o Python darem o mesmo resultado)
ZERO, BAIXO, MEDIO, ALTO = 0, 1, 2, 3

UTIL, SABADO, DOMINGO = "util", "sabado", "domingo"
TIPOS_DIA = (UTIL, SABADO, DOMINGO)
TODOS = TIPOS_DIA
FIM_DE_SEMANA = (SABADO, DOMINGO)

# Expediente da equipe: início entre 7h e 17h, em passos de 30 min; a obra termina até as 18h
EXPEDIENTE_INICIO_MIN = 7 * 60
EXPEDIENTE_ULTIMO_INICIO_MIN = 17 * 60
EXPEDIENTE_FIM_MIN = 18 * 60
PASSO_MIN = 30

# A janela escolhida é "muito pior" que a sugerida a partir desta razão entre as notas
RAZAO_MUITO_PIOR = 1.5


@dataclass(frozen=True)
class Periodo:
    nome: str          # como aparece na explicação ("a ordenha da tarde")
    dias: tuple        # tipos de dia em que vale
    inicio_h: float    # hora de início (inclusive)
    fim_h: float       # hora de fim (exclusive)
    nivel: int


@dataclass(frozen=True)
class Perfil:
    singular: str
    plural: str
    padrao: dict       # nível fora dos períodos, por tipo de dia
    periodos: tuple = ()


PERFIS = {
    "agropecuaria": Perfil(
        "estabelecimento agropecuário", "estabelecimentos agropecuários",
        {UTIL: MEDIO, SABADO: MEDIO, DOMINGO: MEDIO},
        (Periodo("a ordenha da manhã", TODOS, 5, 7, ALTO),
         Periodo("a ordenha da tarde", TODOS, 15, 17, ALTO),
         # IN 77/2018 do MAPA: o leite deve chegar a 4 °C em até 3 horas após o fim da ordenha;
         # sem energia, o tanque não resfria.
         Periodo("o resfriamento do leite da manhã", TODOS, 7, 10, ALTO),
         Periodo("o resfriamento do leite da tarde", TODOS, 17, 20, ALTO))),
    "saude": Perfil(
        "unidade de saúde", "unidades de saúde",
        {UTIL: BAIXO, SABADO: BAIXO, DOMINGO: BAIXO},
        (Periodo("o atendimento de saúde", (UTIL,), 7, 19, ALTO),)),
    "ensino": Perfil(
        "escola", "escolas",
        {UTIL: BAIXO, SABADO: ZERO, DOMINGO: ZERO},
        (Periodo("o horário de aula da manhã", (UTIL,), 7, 12, ALTO),
         Periodo("o horário de aula da tarde", (UTIL,), 13, 17, ALTO))),
    "residencial": Perfil(
        "residência", "residências",
        {UTIL: BAIXO, SABADO: BAIXO, DOMINGO: BAIXO},
        (Periodo("o pico residencial da manhã", TODOS, 6, 8, MEDIO),
         Periodo("o pico residencial da noite", TODOS, 18, 22, MEDIO))),
    "religioso": Perfil(
        "templo", "templos",
        {UTIL: ZERO, SABADO: ZERO, DOMINGO: ZERO},
        (Periodo("a celebração de domingo", (DOMINGO,), 7, 12, MEDIO),)),
    "outros": Perfil(
        "comércio ou serviço", "comércios e serviços",
        {UTIL: ZERO, SABADO: ZERO, DOMINGO: ZERO},
        (Periodo("o horário comercial", TODOS, 8, 18, BAIXO),)),
}
ATIVIDADES = tuple(PERFIS)  # ordem fixa (também usada no mapa)
SENSIVEIS = ("saude", "ensino", "agropecuaria")
