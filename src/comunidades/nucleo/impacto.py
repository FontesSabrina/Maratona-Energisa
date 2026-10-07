"""Janela de menor dano e cargas sensíveis de um desligamento.

Puro: recebe a contagem de UCs afetadas por atividade (nunca nomes) e devolve notas e
sugestões. É uma sugestão para a equipe, que continua decidindo. Os pesos vêm de
perfis_carga.py, que são hipóteses de demonstração.

Tempos em minutos desde a meia-noite. A nota é inteira (quantidade × peso × minutos),
para o navegador reproduzir exatamente o mesmo resultado.
"""

from datetime import date

from . import perfis_carga as P

SLOTS = 24 * 60 // P.PASSO_MIN  # meias horas do dia


def tipo_dia(d: date) -> str:
    return P.UTIL if d.weekday() < 5 else P.SABADO if d.weekday() == 5 else P.DOMINGO


def _min(h: float) -> int:
    return round(h * 60)


def _sobreposicao(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def pesos(atividade: str, tipo: str, perfis: dict | None = None) -> list[int]:
    """Nível de sensibilidade de cada meia hora do dia (o maior entre o padrão e os períodos)."""
    perfil = (perfis or P.PERFIS)[atividade]
    w = []
    for s in range(SLOTS):
        ini = s * P.PASSO_MIN
        nivel = perfil.padrao[tipo]
        for p in perfil.periodos:
            if tipo in p.dias and _min(p.inicio_h) <= ini < _min(p.fim_h):
                nivel = max(nivel, p.nivel)
        w.append(nivel)
    return w


def _nota(contagem: dict, tipo: str, inicio: int, duracao: int, perfis: dict | None = None) -> int:
    fim, total = inicio + duracao, 0
    for atividade in P.ATIVIDADES:
        n = contagem.get(atividade, 0)
        if not n:
            continue
        w = pesos(atividade, tipo, perfis)
        for s in range(SLOTS):
            o = _sobreposicao(inicio, fim, s * P.PASSO_MIN, (s + 1) * P.PASSO_MIN)
            if o:
                total += n * w[s] * o
    return total


def nota_dano(contagem: dict, data: date, inicio: int, duracao: int, perfis: dict | None = None) -> int:
    """Soma, por atividade, quantidade × peso × minutos de cada meia hora dentro da janela."""
    return _nota(contagem, tipo_dia(data), inicio, duracao, perfis)


def inicios_possiveis(duracao: int) -> list[int]:
    if duracao <= 0:
        return []
    ultimo = min(P.EXPEDIENTE_ULTIMO_INICIO_MIN, P.EXPEDIENTE_FIM_MIN - duracao)
    return list(range(P.EXPEDIENTE_INICIO_MIN, ultimo + 1, P.PASSO_MIN))


def _lista(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _qtd(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def explicar(contagem: dict, tipo: str, inicio: int, fim: int, perfis: dict | None = None) -> str:
    """Uma linha: os maiores conflitos da janela e os horários de peso alto que ela evita."""
    perfis = perfis or P.PERFIS
    conflitos, evitados = [], []
    for atividade in P.ATIVIDADES:
        n, perfil = contagem.get(atividade, 0), perfis[atividade]
        if not n:
            continue
        for p in perfil.periodos:
            if tipo not in p.dias:
                continue
            p0, p1 = _min(p.inicio_h), _min(p.fim_h)
            o = _sobreposicao(inicio, fim, p0, p1)
            if o and p.nivel >= P.MEDIO:
                rotulo = perfil.singular if n == 1 else perfil.plural
                conflitos.append((n * p.nivel * o, len(conflitos), f"{p.nome} de {_qtd(n)} {rotulo}"))
            elif not o and p.nivel == P.ALTO and _sobreposicao(P.EXPEDIENTE_INICIO_MIN, P.EXPEDIENTE_FIM_MIN, p0, p1):
                evitados.append(p.nome)
    conflitos.sort(key=lambda c: (-c[0], c[1]))
    pega = [c[2] for c in conflitos[:2]]
    if pega:
        return f"Pega {_lista(pega)}" + (f"; evita {_lista(evitados)}" if evitados else "")
    if evitados:
        return f"Evita {_lista(evitados)}"
    if _nota(contagem, tipo, inicio, fim - inicio, perfis):
        return "Só atinge horários de baixa sensibilidade"
    return "Sem conflito com os horários sensíveis"


def avaliar_janelas(contagem: dict, data: date, duracao: int, perfis: dict | None = None) -> list[dict]:
    """Todas as janelas do expediente, da menor para a maior nota (empate: a que começa antes)."""
    tipo = tipo_dia(data)
    js = [{"inicio": i, "fim": i + duracao, "nota": _nota(contagem, tipo, i, duracao, perfis)}
          for i in inicios_possiveis(duracao)]
    js.sort(key=lambda j: (j["nota"], j["inicio"]))
    for j in js:
        j["tipo"] = tipo
    return js


def sugerir_janelas(contagem: dict, data: date, duracao: int, quantas: int = 3, perfis: dict | None = None) -> list[dict]:
    melhores = avaliar_janelas(contagem, data, duracao, perfis)[:quantas]
    for j in melhores:
        j["explicacao"] = explicar(contagem, j["tipo"], j["inicio"], j["fim"], perfis)
    return melhores


def cargas_sensiveis(contagem: dict) -> dict:
    """Quantas unidades de saúde, escolas e estabelecimentos agropecuários há na área (só contagens)."""
    return {a: int(contagem.get(a, 0)) for a in P.SENSIVEIS}


def perfis_para_mapa() -> dict:
    """Perfis e expediente no formato que o navegador usa para repetir o mesmo cálculo."""
    return {
        "atividades": list(P.ATIVIDADES),
        "pesos": {a: {t: pesos(a, t) for t in P.TIPOS_DIA} for a in P.ATIVIDADES},
        "periodos": {a: [[p.nome, list(p.dias), _min(p.inicio_h), _min(p.fim_h), p.nivel] for p in P.PERFIS[a].periodos]
                     for a in P.ATIVIDADES},
        "rotulos": {a: [P.PERFIS[a].singular, P.PERFIS[a].plural] for a in P.ATIVIDADES},
        "sensiveis": list(P.SENSIVEIS),
        "niveis": {"medio": P.MEDIO, "alto": P.ALTO},
        "expediente": {"inicio": P.EXPEDIENTE_INICIO_MIN, "ultimoInicio": P.EXPEDIENTE_ULTIMO_INICIO_MIN,
                       "fim": P.EXPEDIENTE_FIM_MIN, "passo": P.PASSO_MIN},
        "razaoMuitoPior": P.RAZAO_MUITO_PIOR,
    }
