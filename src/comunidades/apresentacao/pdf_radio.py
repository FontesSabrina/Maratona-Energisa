"""PDF do roteiro para a rádio, gerado no servidor (fpdf2, LGPL-3.0): o que vai anexo no e-mail e o que
o botão "Baixar PDF para a rádio" entrega. Só comunidades, contagens e o texto do aviso: nada de nome
de pessoa, número de UC, endereço ou coordenada.

As fontes embutidas no fpdf2 (Helvetica) cobrem o Latin-1, que tem todos os acentos do português;
travessões, aspas curvas e reticências viram os equivalentes simples.
"""

import hashlib
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

MARCA = Path(__file__).resolve().parent / "marca" / "farol.svg"
NOITE, MARE, AMBAR, CINZA = (14, 22, 32), (28, 42, 55), (245, 184, 61), (90, 102, 112)
_TROCAS = str.maketrans({"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "•": "-", "→": "->",
                         " ": " ", " ": " ", "✓": "", "⇪": ""})


def _l1(texto) -> str:
    """O texto em Latin-1 (o que a fonte embutida desenha); o que sobrar fora vira '?'."""
    return str(texto).translate(_TROCAS).encode("latin-1", "replace").decode("latin-1")


def codigo_texto(texto: str) -> str:
    """Os 16 primeiros caracteres do SHA-256 do texto (o mesmo código que a tela mostra)."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


class _Roteiro(FPDF):
    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*CINZA)
        self.cell(0, 6, _l1(f"Farol - roteiro para a rádio - página {self.page_no()}"), align="C")


def roteiro(*, municipio: str, uf: str, empresa: str, data: str, horario: str, tipo: str, texto: str,
            inteiras: list[str], parciais: list[str], vizinhas: list[str], prazo: str, vital_sim: int, vital_a_confirmar: int,
            solicitado: str, aviso_id: int | None, aviso_ficticio: str, gerado_por: str, gerado_em: datetime) -> bytes:
    pdf = _Roteiro(format="A4", unit="mm")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, 20)
    pdf.set_title(_l1(f"Roteiro para a rádio - {municipio}/{uf} - {data}"))
    pdf.set_author("Farol")
    pdf.set_creator("Farol")
    pdf.add_page()
    # faixa da marca
    pdf.set_fill_color(*NOITE)
    pdf.rect(0, 0, 210, 26, "F")
    try:
        pdf.image(str(MARCA), x=16, y=4, h=18)
    except Exception:  # noqa: BLE001 (sem o logo, o roteiro sai do mesmo jeito)
        pass
    pdf.set_xy(38, 6)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "Farol")
    pdf.set_xy(38, 14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*AMBAR)
    pdf.cell(0, 6, _l1("Cada comunidade avisada pelo nome"))
    pdf.set_y(32)
    pdf.set_text_color(*NOITE)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 9, _l1("Roteiro para a rádio"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 5, _l1(f"{municipio}/{uf} - desligamento programado em {data}, das {horario} - {empresa}"
                             + (f" - {tipo}" if tipo else "")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    def titulo(t):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*MARE)
        pdf.cell(0, 7, _l1(t), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*NOITE)

    titulo("Texto para leitura")
    pdf.set_fill_color(253, 244, 222)
    pdf.set_draw_color(*AMBAR)
    pdf.set_font("Helvetica", "", 13)
    pdf.multi_cell(0, 7, _l1(texto), border=1, fill=True, padding=4, new_x="LMARGIN", new_y="NEXT")
    palavras = len(texto.split())
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*CINZA)
    pdf.cell(0, 6, _l1(f"{palavras} palavras - cerca de {round(palavras / 2.5)} s no ar"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*NOITE)
    pdf.set_font("Helvetica", "", 11)
    for rotulo, nomes in (("Comunidades inteiras", inteiras), ("Parte da comunidade", parciais),
                          ("Localidades vizinhas (citadas em conjunto)", vizinhas)):
        if nomes:
            titulo(rotulo)
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, _l1(", ".join(nomes)), new_x="LMARGIN", new_y="NEXT")
    titulo("Prazo")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, _l1(f"Antecedência mínima: {prazo}."), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 6, _l1(f"Unidades com equipamento vital: {vital_sim}"
                             + (f" ({vital_a_confirmar} a confirmar)" if vital_a_confirmar else "") + " (só a contagem)."),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_draw_color(220, 227, 223)
    pdf.line(18, pdf.get_y(), 192, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(0, 5, _l1(solicitado + (f" - aviso nº {aviso_id}" if aviso_id else "") + "."), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 4.5, _l1(f"PDF gerado em {gerado_em.strftime('%d/%m/%Y às %H:%M')} por {gerado_por}. "
                               f"Código do texto (SHA-256): {codigo_texto(texto)}."), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 4.5, _l1(aviso_ficticio), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
