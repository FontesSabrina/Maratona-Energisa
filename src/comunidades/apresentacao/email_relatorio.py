"""O e-mail de um relatório (botão "Enviar"): o PDF anexo, o título, o código de verificação e quem gerou.

Só para endereços do domínio da empresa (a API confere). Nada de UC, coordenada ou nome de cliente:
o relatório só tem agregados. Todo texto do HTML passa por html.escape.
"""

import html
from email.message import EmailMessage
from email.utils import formatdate, make_msgid


def mensagem(*, remetente: str, destinos: list[str], titulo: str, codigo: str, gerado_por: str, empresa: str,
             pdf: tuple[str, bytes], aviso_ficticio: str) -> EmailMessage:
    m = EmailMessage()
    m["From"], m["To"] = remetente, ", ".join(destinos)
    m["Subject"] = f"Farol: {titulo} ({codigo})"
    m["Date"] = formatdate(localtime=False)
    m["Message-ID"] = make_msgid(domain=remetente.rsplit("@", 1)[-1].strip("> ") or "farol.example")
    m.set_content(f"{empresa}: {titulo}.\n\nGerado por {gerado_por}. Código de verificação: {codigo}.\n"
                  f"O PDF vai anexo; a segunda via fica guardada no Farol, com o mesmo SHA-256.\n\n{aviso_ficticio}\n")
    e = html.escape
    m.add_alternative(f"""<!doctype html><html lang="pt-BR"><body style="font-family:Arial,sans-serif;color:#0E1620">
<p><b>{e(empresa)}</b>: {e(titulo)}.</p><p>Gerado por {e(gerado_por)}. Código de verificação: <b>{e(codigo)}</b>.</p>
<p>O PDF vai anexo; a segunda via fica guardada no Farol, com o mesmo SHA-256.</p>
<p style="color:#5A6670;font-size:12px">{e(aviso_ficticio)}</p></body></html>""", subtype="html")
    m.add_attachment(pdf[1], maintype="application", subtype="pdf", filename=pdf[0])
    return m
