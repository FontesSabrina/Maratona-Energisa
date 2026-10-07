"""Desafio 3: identificar as comunidades afetadas por um desligamento programado."""


def main() -> None:
    """Comando `comunidades`: executa o pipeline (ver pipeline.py)."""
    import sys

    from .pipeline import executar

    executar(sys.argv)
