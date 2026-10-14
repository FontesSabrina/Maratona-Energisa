"""Consultas dos relatórios: avisos e envios de um período e linhas da auditoria (só agregados e registros)."""

from datetime import date, datetime, time, timedelta, timezone

from psycopg.rows import dict_row

from .acesso import AVISO
from .conexao import conectar
from .radios import ENVIO

BRASILIA = timezone(timedelta(hours=-3))


def _todos(sql: str, args=()) -> list[dict]:
    with conectar() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def _intervalo(inicio: date, fim: date) -> tuple[datetime, datetime]:
    """Do começo do primeiro dia ao fim do último, no horário de Brasília."""
    return datetime.combine(inicio, time.min, BRASILIA), datetime.combine(fim + timedelta(days=1), time.min, BRASILIA)


def avisos(empresa_id: int, inicio: date, fim: date) -> list[dict]:
    a, b = _intervalo(inicio, fim)
    return _todos(f"SELECT {AVISO} FROM aviso a LEFT JOIN usuario u ON u.id = a.usuario_id"
                  " WHERE a.empresa_id = %s AND a.criado_em >= %s AND a.criado_em < %s ORDER BY a.criado_em", (empresa_id, a, b))


def envios(empresa_id: int, aviso_ids: list[int]) -> list[dict]:
    if not aviso_ids:
        return []
    return _todos(f"SELECT {ENVIO} FROM envio e WHERE e.empresa_id = %s AND e.aviso_id = ANY(%s) ORDER BY e.id",
                  (empresa_id, list(aviso_ids)))


def registros(empresa_id: int | None, inicio: date, fim: date, pessoa: str | None = None, acoes: tuple[str, ...] | None = None,
              empresa_sigla: str | None = None, limite: int = 5000) -> list[dict]:
    """Linhas da auditoria do período (da empresa, ou de todas com empresa_id None), da mais antiga à mais recente."""
    a, b = _intervalo(inicio, fim)
    filtros, args = ["r.quando >= %s", "r.quando < %s"], [a, b]
    if empresa_id is not None:
        filtros.append("r.empresa_id = %s")
        args.append(empresa_id)
    if empresa_sigla:
        filtros.append("e.sigla = %s")
        args.append(empresa_sigla)
    if pessoa:
        filtros.append("r.usuario_nome = %s")
        args.append(pessoa)
    if acoes:
        filtros.append("r.acao = ANY(%s)")
        args.append(list(acoes))
    return _todos("SELECT r.id, r.quando, r.acao, r.detalhe, r.usuario_nome AS usuario, r.perfil, r.hash, e.sigla AS empresa"
                  " FROM registro r LEFT JOIN empresa e ON e.id = r.empresa_id WHERE " + " AND ".join(filtros)
                  + " ORDER BY r.id LIMIT %s", (*args, limite))
