"""Simulação de desligamento programado e geração do aviso de rádio (antes x depois)."""

import re
from dataclasses import dataclass, field

import pandas as pd

LIMIAR_TOTAL = 0.9       # >= 90% das UCs da comunidade afetadas -> comunidade inteira
PALAVRAS_POR_SEGUNDO = 2.5  # locução de rádio ~150 palavras/min


@dataclass
class Desligamento:
    chave: str
    ucs: pd.DataFrame                    # UCs afetadas (com COMUNIDADE_PREVISTA)
    comunidades: pd.DataFrame = field(default=None)
    aviso_antigo: str = ""
    aviso_novo: str = ""


def ucs_afetadas(ucs: pd.DataFrame, chave: str) -> pd.DataFrame:
    alvo = ucs["CHAVES_MONTANTE"].fillna("").str.contains(rf"(?:^|;){re.escape(chave)}(?:;|$)")
    return ucs[alvo]


def _lista(itens: list[str]) -> str:
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _sem_sufixo(nome: str) -> str:
    return re.sub(r" \(.*\)$", "", nome)


def resumir(afetadas: pd.DataFrame, todas: pd.DataFrame) -> pd.DataFrame:
    total = todas["COMUNIDADE_PREVISTA"].value_counts()
    c = afetadas.groupby("COMUNIDADE_PREVISTA").agg(
        UC_AFETADAS=("UC", "count"), CONFIANCA=("CONFIANCA", "mean"), DISTRITO=("DISTRITO", lambda s: s.mode().iat[0])
    )
    c["UC_TOTAL"] = total.reindex(c.index).to_numpy()
    c["PARCIAL"] = c["UC_AFETADAS"] / c["UC_TOTAL"] < LIMIAR_TOTAL
    return c.sort_values("UC_AFETADAS", ascending=False).reset_index()


def locais_antigos(afetadas: pd.DataFrame) -> list[str]:
    """Como o sistema cita hoje: o imóvel (rural) ou a rua (urbano) de cada UC, sem repetir."""
    locais = afetadas["NOME_IMOVEL"].where(afetadas["NOME_IMOVEL"].fillna("") != "", afetadas["LOGRADOURO"])
    return [l.title() for l in pd.unique(locais.dropna())]


def aviso_antigo(afetadas: pd.DataFrame, data: str, horario: str) -> str:
    """O aviso como é hoje: imóvel por imóvel (rural) e rua por rua (urbano)."""
    return (f"Atenção! A Energisa informa desligamento programado no dia {data}, das {horario}, "
            f"para manutenção na rede elétrica, atingindo: {_lista(locais_antigos(afetadas))}.")


def aviso_novo(resumo: pd.DataFrame, data: str, horario: str) -> str:
    nomes = resumo["COMUNIDADE_PREVISTA"].map(_sem_sufixo)
    inteiras = list(dict.fromkeys(nomes[~resumo["PARCIAL"]]))
    parciais = [n for n in dict.fromkeys(nomes[resumo["PARCIAL"]]) if n not in inteiras]
    quem = _lista(inteiras)
    if parciais:
        quem = f"{quem}, e de parte de {_lista(parciais)}" if quem else f"parte de {_lista(parciais)}"
    distritos = sorted({"Sede" if d == "Leopoldina" else d for d in resumo["DISTRITO"]})
    onde = f"distrito{'s' if len(distritos) > 1 else ''} {_lista(distritos)}"
    return (f"Atenção, moradores de {quem}, em Leopoldina ({onde}): "
            f"no dia {data}, das {horario}, haverá desligamento programado de energia para "
            f"manutenção na rede. Programe-se!")


def duracao_s(texto: str) -> float:
    return len(texto.split()) / PALAVRAS_POR_SEGUNDO


def simular(ucs: pd.DataFrame, chave: str, data="12/11", horario="8h às 14h") -> Desligamento:
    afet = ucs_afetadas(ucs, chave)
    d = Desligamento(chave=chave, ucs=afet)
    d.comunidades = resumir(afet, ucs)
    d.aviso_antigo = aviso_antigo(afet, data, horario)
    d.aviso_novo = aviso_novo(d.comunidades, data, horario)
    return d
