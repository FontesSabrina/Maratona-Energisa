"""Texto do aviso como deve ser falado (para a voz sintetizada).

Puro. O aviso escrito usa formas curtas que a voz leria errado: "8h" sairia "oito agá" e "20/11",
"vinte barra onze". Aqui elas viram o que o locutor diria: "8 horas", "20 de novembro".
Os números continuam em algarismos: a própria voz os lê por extenso.
"""

import re

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def _hora(m: re.Match) -> str:
    h, mi = int(m.group(1)), m.group(2)
    horas = "hora" if h == 1 else "horas"
    if not mi or int(mi) == 0:
        return f"{h} {horas}"
    return f"{h} {horas} e {int(mi)}"


def _data(m: re.Match) -> str:
    d, mes = int(m.group(1)), int(m.group(2))
    if not (1 <= d <= 31 and 1 <= mes <= 12):
        return m.group(0)
    dia = "primeiro" if d == 1 else str(d)
    return f"{dia} de {MESES[mes - 1]}" + (f" de {m.group(3)}" if m.group(3) else "")


def texto_para_fala(texto: str) -> str:
    t = " ".join(str(texto).split())
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", _data, t)       # 20/11 -> 20 de novembro
    t = re.sub(r"\b(\d{1,2})h(?:(\d{2})(?:min)?)?\b", _hora, t)          # 8h -> 8 horas; 14h30 -> 14 horas e 30
    t = re.sub(r"\bnº\s*", "número ", t)
    return t
