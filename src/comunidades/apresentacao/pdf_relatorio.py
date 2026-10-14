"""PDF dos relatórios (mensal, comprovante do aviso, auditoria), no visual do Farol (fpdf2, fontes Latin-1).

Recebe o título, quem gerou, o código de verificação (que aponta para a linha da auditoria que
registrou o relatório) e as seções: parágrafos, números (rótulo e valor) e tabelas. Todo texto passa
pelo _l1 (Latin-1), como no roteiro da rádio.
"""

from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from .pdf_radio import AMBAR, CINZA, MARCA, MARE, NOITE, _l1


class _Relatorio(FPDF):
    rodape = ""

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*CINZA)
        self.cell(0, 6, _l1(f"{self.rodape} - página {self.page_no()}"), align="C")


def documento(titulo: str, subtitulo: str, gerado_por: str, codigo: str, secoes: list[tuple], aviso_ficticio: str,
              gerado_em: datetime, paisagem: bool = False) -> bytes:
    """secoes: ("titulo", texto) | ("texto", texto) | ("numeros", [(rotulo, valor), ...]) | ("tabela", cabecalho, linhas[, larguras])."""
    pdf = _Relatorio(orientation="L" if paisagem else "P", format="A4", unit="mm")
    largura = 297 if paisagem else 210
    pdf.rodape = f"Farol - {titulo} - código {codigo}"
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(True, 18)
    pdf.set_title(_l1(titulo))
    pdf.set_author("Farol")
    pdf.add_page()
    pdf.set_fill_color(*NOITE)
    pdf.rect(0, 0, largura, 24, "F")
    pdf.set_fill_color(255, 255, 255)   # o fundo das tabelas (o fpdf2 usa a cor de preenchimento atual)
    try:
        pdf.image(str(MARCA), x=12, y=3.5, h=17)
    except Exception:  # noqa: BLE001
        pass
    pdf.set_xy(33, 5)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, "Farol")
    pdf.set_xy(33, 13)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*AMBAR)
    pdf.cell(0, 6, _l1("Cada comunidade avisada pelo nome"))
    pdf.set_y(29)
    pdf.set_text_color(*NOITE)
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 8, _l1(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 5, _l1(subtitulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*MARE)
    pdf.multi_cell(0, 5, _l1(f"Gerado por {gerado_por} em {gerado_em:%d/%m/%Y às %H:%M} - código de verificação {codigo}"),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    cabeca = FontFace(emphasis="BOLD", fill_color=(233, 238, 243))
    for s in secoes:
        tipo = s[0]
        if tipo == "titulo":
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11.5)
            pdf.set_text_color(*MARE)
            pdf.multi_cell(0, 6.5, _l1(s[1]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*NOITE)
        elif tipo == "texto":
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(0, 5, _l1(s[1]), new_x="LMARGIN", new_y="NEXT")
        elif tipo == "numeros":
            pdf.set_font("Helvetica", "", 9.5)
            with pdf.table(col_widths=(2, 1), text_align=("LEFT", "RIGHT"), first_row_as_headings=False,
                           line_height=5.5, borders_layout="HORIZONTAL_LINES") as t:
                for rotulo, valor in s[1]:
                    linha = t.row()
                    linha.cell(_l1(rotulo))
                    linha.cell(_l1(valor))
        elif tipo == "tabela":
            cab, linhas = s[1], s[2]
            if not linhas:
                pdf.set_font("Helvetica", "I", 9)
                pdf.multi_cell(0, 5, _l1("Nada neste período."), new_x="LMARGIN", new_y="NEXT")
                continue
            pdf.set_font("Helvetica", "", 8)
            larguras = s[3] if len(s) > 3 else None
            with pdf.table(headings_style=cabeca, line_height=4.6, borders_layout="SINGLE_TOP_LINE", repeat_headings=1,
                           col_widths=larguras) as t:
                h = t.row()
                for c in cab:
                    h.cell(_l1(c))
                for ln in linhas:
                    r = t.row()
                    for v in ln:
                        r.cell(_l1("" if v is None else v))
        pdf.ln(1.5)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 4.2, _l1("Só números agregados e o que está gravado: nenhum nome de cliente, número de UC, endereço ou "
                               "coordenada. Confira o código de verificação na auditoria do Farol. " + aviso_ficticio),
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
