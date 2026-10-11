"""Modelos do aviso de rádio por idioma (pt-BR, en, es). Puro: só dados e formatação.

O navegador recebe estes mesmos modelos (ver para_mapa) e repete as mesmas regras,
para o texto sair idêntico nos dois lados. Os nomes das comunidades, dos distritos
e do município nunca são traduzidos.
"""

import unicodedata

MESES_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
            "September", "October", "November", "December"]

IDIOMAS = {
    "pt-BR": {
        "nome": "Português", "voz": "pt-BR",
        "e": " e ", "e_antes_de_i": " e ",
        "parte_com": "{quem}, e de parte de {parciais}", "parte_so": "parte de {parciais}",
        "parte_com_vizinhas": "{quem}, e de parte de {parciais}",
        "vizinhas": "{quem}, além de localidades vizinhas",
        "onde_1": "distrito {distritos}", "onde_n": "distritos {distritos}",
        "frase": ("Atenção, moradores de {quem}, em {municipio} ({onde}): no dia {data}, das {horario}, "
                  "haverá desligamento programado de energia para manutenção na rede. Programe-se!"),
        "telefone": " Dúvidas: {telefone}.",
        "data": "dd/mm", "relogio": "pt", "entre": " às ",
    },
    "en": {
        "nome": "English", "voz": "en-US",
        "e": " and ", "e_antes_de_i": " and ",
        "parte_com": "{quem}, and part of {parciais}", "parte_so": "part of {parciais}",
        # com vizinhas, vira uma lista de três partes com um "and" só antes da última
        "parte_com_vizinhas": "{quem}, part of {parciais}",
        "vizinhas": "{quem}, and nearby areas",
        "onde_1": "{distritos} district", "onde_n": "{distritos} districts",
        "frase": ("Attention, residents of {quem}, in {municipio} ({onde}): on {data}, from {horario}, "
                  "there will be a scheduled power outage for grid maintenance. Please plan ahead!"),
        "telefone": " For questions, call {telefone}.",
        "data": "mes_dia", "relogio": "12h", "entre": " to ",
    },
    "es": {
        "nome": "Español", "voz": "es-ES",
        "e": " y ", "e_antes_de_i": " e ",   # "y" vira "e" antes de som de "i" (Itamarati -> "e Itamarati")
        "parte_com": "{quem}, y de parte de {parciais}", "parte_so": "parte de {parciais}",
        "parte_com_vizinhas": "{quem}, y de parte de {parciais}",
        "vizinhas": "{quem}, además de localidades vecinas",
        "onde_1": "distrito {distritos}", "onde_n": "distritos {distritos}",
        "frase": ("Atención, vecinos de {quem}, en {municipio} ({onde}): el día {data}, de {horario}, "
                  "habrá un corte programado de energía por mantenimiento de la red. ¡Prepárese!"),
        "telefone": " Consultas: {telefone}.",
        "data": "dd/mm", "relogio": "24h", "entre": " a ",
    },
}
PADRAO = "pt-BR"


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def _som_de_i(palavra: str) -> bool:
    """Começa com som de "i" (i-, hi-), sem formar ditongo (hielo, hierba)."""
    s = _sem_acento(palavra)
    if s.startswith("hi"):
        s = s[1:]
    return s.startswith("i") and s[1:2] not in ("a", "e", "o", "u")


def lista(itens: list[str], idioma: str) -> str:
    m = IDIOMAS[idioma]
    if len(itens) <= 1:
        return "".join(itens)
    conj = m["e_antes_de_i"] if _som_de_i(itens[-1]) else m["e"]
    return ", ".join(itens[:-1]) + conj + itens[-1]


def formatar_data(dia: int, mes: int, idioma: str) -> str:
    if IDIOMAS[idioma]["data"] == "mes_dia":
        return f"{MESES_EN[mes - 1]} {dia}"
    return f"{dia:02d}/{mes:02d}"


def formatar_hora(minutos: int, idioma: str) -> str:
    h, m = divmod(minutos, 60)
    relogio = IDIOMAS[idioma]["relogio"]
    if relogio == "pt":
        return f"{h}h" + (f"{m:02d}" if m else "")
    if relogio == "12h":
        return f"{h % 12 or 12}:{m:02d} {'a.m.' if h < 12 else 'p.m.'}"
    return f"{h}:{m:02d}"


def formatar_horario(inicio: int, fim: int, idioma: str) -> str:
    return formatar_hora(inicio, idioma) + IDIOMAS[idioma]["entre"] + formatar_hora(fim, idioma)


def montar(inteiras: list[str], parciais: list[str], tem_vizinhas: bool, distritos: list[str],
           municipio: str, data: str, horario: str, idioma: str = PADRAO) -> str:
    """Texto do aviso a partir das listas já decididas pelas regras do produto."""
    m = IDIOMAS[idioma]
    quem = lista(inteiras, idioma)
    if parciais:
        modelo = (m["parte_com_vizinhas"] if tem_vizinhas else m["parte_com"]) if quem else m["parte_so"]
        quem = modelo.format(quem=quem, parciais=lista(parciais, idioma))
    if tem_vizinhas:
        quem = m["vizinhas"].format(quem=quem)
    onde = (m["onde_n"] if len(distritos) > 1 else m["onde_1"]).format(distritos=lista(distritos, idioma))
    return m["frase"].format(quem=quem, municipio=municipio, onde=onde, data=data, horario=horario)


def com_telefone(texto: str, telefone: str, idioma: str = PADRAO) -> str:
    return texto + IDIOMAS[idioma]["telefone"].format(telefone=telefone) if telefone else texto


def para_mapa() -> dict:
    return {"modelos": IDIOMAS, "mesesEn": MESES_EN, "padrao": PADRAO}
