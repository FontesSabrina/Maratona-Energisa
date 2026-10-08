"""Página de entrada do Farol (saida/index.html): abertura e a escolha da área.

Lista os municípios já processados, lendo os resumo_mapa.json que cada mapa grava ao lado
(só nome, UF e contagens). Os links são relativos, para funcionar aberta como arquivo, sem
servidor. A página não tem script: a abertura é só CSS, e a CSP é a dos mapas com script-src 'none'.

Uso: py -m uv run python -m comunidades.apresentacao.entrada (o pipeline já roda no fim)
"""

import json
from html import escape
from pathlib import Path

from .mapa import ARQ_RESUMO, SAIDA_RAIZ, _fontes_embutidas, favicon, logo_com_feixe, politica_seguranca

TEMPLATE = Path(__file__).with_name("entrada_template.html")
ARQ_ENTRADA = SAIDA_RAIZ / "index.html"


def municipios() -> list[dict]:
    """Resumos dos mapas já gerados: saida/ (o primeiro município) e saida/<municipio>/, em ordem alfabética."""
    arquivos = [SAIDA_RAIZ / ARQ_RESUMO.name, *sorted(SAIDA_RAIZ.glob(f"*/{ARQ_RESUMO.name}"))]
    lista = [json.loads(a.read_text(encoding="utf-8")) for a in arquivos if a.exists()]
    return sorted((m for m in lista if (SAIDA_RAIZ / m["mapa"]).exists()), key=lambda m: m["municipio"])


def _n(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def _cartao(m: dict) -> str:
    nome, uf = escape(m["municipio"]), escape(m["uf"])
    return f"""
      <li class="cartao">
        <div class="cartao-cab"><h2>{nome}</h2><span class="uf">{uf}</span></div>
        <dl class="numeros">
          <div><dt>clientes</dt><dd>{_n(m["clientes"])}</dd></div>
          <div><dt>comunidades</dt><dd>{_n(m["comunidades"])}</dd></div>
          <div><dt>chaves</dt><dd>{_n(m["chaves"])}</dd></div>
        </dl>
        <a class="abrir" href="{escape(m["mapa"])}" aria-label="Abrir {nome}/{uf}">Abrir</a>
      </li>"""


def construir() -> Path:
    ms = municipios()
    cartoes = (f'<ul class="cartoes">{"".join(_cartao(m) for m in ms)}\n    </ul>' if ms
               else '<p class="vazio">Nenhuma área gerada ainda. Rode o Farol para um município.</p>')
    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("<!--__LOGO__-->", logo_com_feixe())
            .replace("__FAVICON__", favicon())
            .replace("/*__FONTES__*/", _fontes_embutidas())
            .replace("<!--__CARTOES__-->", cartoes))
    html = html.replace("/*__CSP__*/", politica_seguranca(html))
    ARQ_ENTRADA.write_text(html, encoding="utf-8", newline="\n")
    return ARQ_ENTRADA


if __name__ == "__main__":
    p = construir()
    print(f"Entrada: {p} ({len(municipios())} áreas)")
