"""Simulação de desligamento programado e geração do aviso de rádio (antes x depois).

Puro: limites, município e assinatura vêm da configuração da distribuidora (RegrasAviso),
e o texto do aviso vem dos modelos por idioma (idiomas.py).
"""

import re
from dataclasses import dataclass, field

import pandas as pd

from . import idiomas

# Locução de rádio ~150 palavras/min. É uma aproximação, usada para todos os idiomas.
PALAVRAS_POR_SEGUNDO = 2.5


@dataclass(frozen=True)
class RegrasAviso:
    limiar_total: float          # >= esta fração das UCs da comunidade afetadas -> comunidade inteira
    # Comunidade atingida só em parte, com poucas UCs afetadas e pouco peso no ramal, é quase
    # sempre ruído da votação na fronteira (fragmento). Ela não é citada pelo nome: o aviso diz
    # "além de localidades vizinhas", para que essas poucas UCs não fiquem sem aviso.
    limite_fragmento: int        # até tantas UCs afetadas...
    limite_participacao: float   # ...e menos desta fração das UCs desligadas pela chave
    municipio: str               # citado no aviso; o distrito com este nome vira "Sede"
    assinatura_aviso_atual: str  # quem assina o aviso de hoje ("A Energisa informa...")


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


def _sem_sufixo(nome: str) -> str:
    return re.sub(r" \(.*\)$", "", nome)


def resumir(afetadas: pd.DataFrame, todas: pd.DataFrame, regras: RegrasAviso) -> pd.DataFrame:
    total = todas["COMUNIDADE_PREVISTA"].value_counts()
    c = afetadas.groupby("COMUNIDADE_PREVISTA").agg(
        UC_AFETADAS=("UC", "count"), CONFIANCA=("CONFIANCA", "mean"), DISTRITO=("DISTRITO", lambda s: s.mode().iat[0])
    )
    c["UC_TOTAL"] = total.reindex(c.index).to_numpy()
    c["PARCIAL"] = c["UC_AFETADAS"] / c["UC_TOTAL"] < regras.limiar_total
    c = c.sort_values("UC_AFETADAS", ascending=False).reset_index()
    c["FRAGMENTO"] = (c["PARCIAL"] & (c["UC_AFETADAS"] <= regras.limite_fragmento)
                      & (c["UC_AFETADAS"] / c["UC_AFETADAS"].sum() < regras.limite_participacao))
    if len(c) and c["FRAGMENTO"].all():  # ramal minúsculo: cita ao menos a comunidade maior
        c.loc[0, "FRAGMENTO"] = False
    return c


def locais_antigos(afetadas: pd.DataFrame) -> list[str]:
    """Como o sistema cita hoje: o imóvel (rural) ou a rua (urbano) de cada UC, sem repetir."""
    locais = afetadas["NOME_IMOVEL"].where(afetadas["NOME_IMOVEL"].fillna("") != "", afetadas["LOGRADOURO"])
    return [l.title() for l in pd.unique(locais.dropna())]


def aviso_antigo(afetadas: pd.DataFrame, data: str, horario: str, regras: RegrasAviso) -> str:
    """O aviso como é hoje (em português): imóvel por imóvel (rural) e rua por rua (urbano)."""
    return (f"Atenção! A {regras.assinatura_aviso_atual} informa desligamento programado no dia {data}, "
            f"das {horario}, para manutenção na rede elétrica, atingindo: "
            f"{idiomas.lista(locais_antigos(afetadas), 'pt-BR')}.")


def partes_do_aviso(resumo: pd.DataFrame, municipio: str) -> tuple:
    """Inteiras, parciais, se há vizinhas e os distritos, já decididos pelas regras do produto."""
    citadas = resumo[~resumo["FRAGMENTO"]]
    nomes = citadas["COMUNIDADE_PREVISTA"].map(_sem_sufixo)
    inteiras = list(dict.fromkeys(nomes[~citadas["PARCIAL"]]))
    parciais = [n for n in dict.fromkeys(nomes[citadas["PARCIAL"]]) if n not in inteiras]
    distritos = sorted({"Sede" if d == municipio else d for d in resumo["DISTRITO"]})
    return inteiras, parciais, bool(resumo["FRAGMENTO"].any()), distritos


def aviso_novo(resumo: pd.DataFrame, data: str, horario: str, regras: RegrasAviso,
               idioma: str = idiomas.PADRAO) -> str:
    inteiras, parciais, vizinhas, distritos = partes_do_aviso(resumo, regras.municipio)
    return idiomas.montar(inteiras, parciais, vizinhas, distritos, regras.municipio, data, horario, idioma)


def duracao_s(texto: str) -> float:
    return len(texto.split()) / PALAVRAS_POR_SEGUNDO


def simular(ucs: pd.DataFrame, chave: str, regras: RegrasAviso, data="12/11", horario="8h às 14h") -> Desligamento:
    afet = ucs_afetadas(ucs, chave)
    d = Desligamento(chave=chave, ucs=afet)
    d.comunidades = resumir(afet, ucs, regras)
    d.aviso_antigo = aviso_antigo(afet, data, horario, regras)
    d.aviso_novo = aviso_novo(d.comunidades, data, horario, regras)
    return d
