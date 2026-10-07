"""Desafio 3: identificar as comunidades afetadas por um desligamento programado."""


def main() -> None:
    """Executa o pipeline completo: dados reais -> rede fictícia -> algoritmo -> avaliação -> mapa."""
    import sys

    from . import algoritmo, avaliacao, clientes, dados, ibge, mapa, osm, rede

    etapas = [
        ("Dados do IBGE (download na primeira vez)", dados.garantir),
        ("IBGE: camadas reais e gabarito", ibge.construir),
        ("OSM: malha viária", osm.carregar),
        ("Rede elétrica fictícia", rede.construir),
        ("Cadastro fictício de UCs", clientes.construir),
        ("Algoritmo de comunidades", algoritmo.construir),
        ("Mapa interativo (inclui avaliação)", mapa.construir),
    ]
    pular_dados = "--so-algoritmo" in sys.argv
    for nome, f in etapas:
        if pular_dados and f in (dados.garantir, ibge.construir, osm.carregar, rede.construir, clientes.construir):
            continue
        print(f"> {nome}...", flush=True)
        f()

    _, por_uc, _, cen = avaliacao.avaliar()
    print("\nAcerto por UC (cadastro digitado x algoritmo):")
    print(por_uc.to_string())
    print(f"\nCenários: {len(cen)} | cobertura média {cen.COBERTURA.mean():.1%} | "
          f"precisão média {cen.PRECISAO.mean():.1%} | aviso {cen.SEG_ANTES.mean():.0f}s -> {cen.SEG_DEPOIS.mean():.0f}s")
    print(f"\nMapa: {mapa.ARQ_SAIDA}")
