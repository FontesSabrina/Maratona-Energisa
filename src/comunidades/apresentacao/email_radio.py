"""O e-mail do aviso para a rádio: o texto para leitura, o PDF e o MP3 anexos e o botão "Confirmar recebimento".

Só o que a rádio precisa: o texto do aviso (comunidades, data, horário, motivo), o município e o
código de verificação. Nada de nome de pessoa, número de UC, endereço ou coordenada. Todo texto do
HTML passa por html.escape. O link de confirmação leva um token aleatório de uso único (7 dias).
"""

import html
from email.message import EmailMessage
from email.utils import formatdate, make_msgid


def mensagem(*, remetente: str, destino: str, municipio: str, uf: str, data: str, horario: str, empresa: str,
             texto: str, codigo: str, link_confirmar: str, pdf: tuple[str, bytes] | None, mp3: tuple[str, bytes] | None,
             aviso_ficticio: str) -> EmailMessage:
    m = EmailMessage()
    m["From"], m["To"] = remetente, destino
    m["Subject"] = f"Aviso de desligamento programado: {municipio}/{uf}, {data} ({codigo})"
    m["Date"] = formatdate(localtime=False)
    m["Message-ID"] = make_msgid(domain=remetente.rsplit("@", 1)[-1].strip("> ") or "farol.example")
    corpo = (f"{empresa}: aviso de desligamento programado para leitura no ar.\n\n"
             f"Município: {municipio}/{uf}\nData: {data}, das {horario}\nCódigo de verificação: {codigo}\n\n"
             f"Texto para leitura:\n\n{texto}\n\n"
             f"O roteiro (PDF){' e o áudio (MP3)' if mp3 else ''} vão anexos.\n\n"
             f"Confirme o recebimento neste link (vale 7 dias, uma vez):\n{link_confirmar}\n\n"
             f"{aviso_ficticio}\n")
    m.set_content(corpo)
    e = html.escape
    m.add_alternative(f"""<!doctype html><html lang="pt-BR"><body style="margin:0;background:#E9EEF3;font-family:Arial,sans-serif;color:#0E1620">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#FFFFFF;border-radius:12px;overflow:hidden">
<tr><td style="background:#0E1620;padding:18px 24px;color:#FFFFFF;font-size:20px;font-weight:bold">Farol
<div style="color:#F5B83D;font-size:13px;font-weight:normal">Cada comunidade avisada pelo nome</div></td></tr>
<tr><td style="padding:24px">
<p style="margin:0 0 8px">{e(empresa)}: aviso de desligamento programado para leitura no ar.</p>
<p style="margin:0 0 16px;color:#1C2A37"><b>{e(municipio)}/{e(uf)}</b> · {e(data)}, das {e(horario)} · código <b>{e(codigo)}</b></p>
<p style="margin:0 0 6px;font-weight:bold">Texto para leitura</p>
<p style="margin:0 0 20px;padding:14px;background:#FDF4DE;border:1px solid #F5B83D;border-radius:8px;font-size:16px;line-height:1.5">{e(texto)}</p>
<p style="margin:0 0 20px">O roteiro (PDF){" e o áudio (MP3)" if mp3 else ""} vão anexos.</p>
<p style="margin:0 0 20px"><a href="{e(link_confirmar, quote=True)}" style="display:inline-block;background:#F5B83D;color:#0E1620;font-weight:bold;text-decoration:none;padding:14px 22px;border-radius:8px">Confirmar recebimento</a></p>
<p style="margin:0;color:#5A6670;font-size:12px">O link vale 7 dias e uma vez. {e(aviso_ficticio)}</p>
</td></tr></table></td></tr></table></body></html>""", subtype="html")
    if pdf:
        m.add_attachment(pdf[1], maintype="application", subtype="pdf", filename=pdf[0])
    if mp3:
        m.add_attachment(mp3[1], maintype="audio", subtype="mpeg", filename=mp3[0])
    return m
