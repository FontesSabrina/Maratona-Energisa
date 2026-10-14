"""Relatórios: o do período (mensal), o comprovante de um aviso, o de auditoria da empresa e o de acessos (geral).

- Mensal e comprovante: os três perfis da empresa (Admin, Operador e Consulta), só da própria empresa.
- Auditoria da empresa: só o Admin da empresa. Acessos de todas as empresas: só o Admin do Farol.
- Filtros: período (mês ou de/até), município, tipo, rádio e pessoa.
- Exportar em PDF ou CSV (CSV protegido contra fórmula): cada exportação vira uma linha da auditoria
  ("gerou relatório ...") com o nome de quem gerou, e o código de verificação do relatório sai do hash
  dessa linha (FRL-...; /api/verificar/{codigo} confere).
Só agregados e o que está gravado: nada de UC, coordenada ou nome de cliente.
"""

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..apresentacao import pdf_relatorio
from ..banco import acesso as banco_acesso
from ..banco import relatorios as banco
from ..nucleo import relatorio as R
from ..nucleo.acesso import PERFIS
from ..nucleo.auditoria import codigo_verificacao
from ..nucleo.tipos_desligamento import ROTULOS
from .acesso import exigir
from .comum import AVISO_FICTICIO, BRASILIA, DIST

rotas = APIRouter()
MAX_DIAS = 400
ACESSOS = ("entrou", "saiu", "senha errada", "senha errada (conta bloqueada por 15 min)", "login recusado (conta em bloqueio temporário)",
           "login recusado (usuário bloqueado ou empresa suspensa)", "trocou a senha", "gerou senha temporária",
           "semente: nova senha temporária")
STATUS = {"preparando": "preparando", "enviado": "enviado", "entregue": "entregue", "falhou": "falhou", "confirmado": "confirmado"}


def _periodo(mes: str | None, inicio: str | None, fim: str | None) -> tuple[date, date, bool]:
    """(início, fim, é um mês inteiro). Padrão: o mês corrente."""
    try:
        if inicio or fim:
            i, f = date.fromisoformat(inicio or fim), date.fromisoformat(fim or inicio)
            mes_inteiro = False
        else:
            i, f = R.periodo_do_mes(mes or datetime.now(BRASILIA).strftime("%Y-%m"))
            mes_inteiro = True
    except (ValueError, TypeError):
        raise HTTPException(422, "Período: use mes=AAAA-MM ou inicio e fim no formato AAAA-MM-DD.") from None
    if f < i or (f - i).days > MAX_DIAS:
        raise HTTPException(422, f"Período: o fim depois do início, até {MAX_DIAS} dias.")
    return i, f, mes_inteiro


def _brl(v) -> str:
    s = f"{Decimal(str(v)):,.2f}"
    return "R$ " + s.replace(",", "_").replace(".", ",").replace("_", ".")


def _tempo(s) -> str:
    s = int(s or 0)
    sinal, s = ("-" if s < 0 else ""), abs(s)
    return f"{sinal}{s // 60} min {s % 60:02d} s" if s >= 60 else f"{sinal}{s} s"


def _registrar(u: dict, o_que: str, detalhe: str) -> str:
    """A linha da auditoria do relatório; o código de verificação sai do hash dela."""
    return codigo_verificacao(banco_acesso.registrar(o_que, detalhe[:500], u["id"], u["empresa_id"])["hash"])


def _quem(u: dict) -> str:
    return f"{u['nome']} ({PERFIS[u['perfil']]})"


# ---------- Mensal (ou de um período) ----------
def _mensal(u: dict, mes, inicio, fim, municipio, tipo, radio, pessoa) -> dict:
    i, f, mes_inteiro = _periodo(mes, inicio, fim)
    filtros = {"municipio": municipio, "tipo": tipo, "radio": radio, "pessoa": pessoa}
    avisos = banco.avisos(u["empresa_id"], i, f)
    envios = banco.envios(u["empresa_id"], [a["id"] for a in avisos])
    rel = R.mensal(avisos, envios, i, f, filtros, DIST.prazo_legal_horas, DIST.prazo_vital_dias_uteis)
    if mes_inteiro:
        ai, af = R.periodo_do_mes(R.mes_anterior(i))
        av_ant = banco.avisos(u["empresa_id"], ai, af)
        ant = R.mensal(av_ant, banco.envios(u["empresa_id"], [a["id"] for a in av_ant]), ai, af, filtros,
                       DIST.prazo_legal_horas, DIST.prazo_vital_dias_uteis)
        rel["comparacao"] = {"periodo": ant["periodo"]["rotulo"], "numeros": R.comparar(rel, ant)}
    rel["opcoes"] = {   # o que dá para filtrar neste período (da própria empresa)
        "municipios": sorted({(m["codigo_ibge"], f"{m['nome']}/{m['uf']}") for a in avisos for m in a["municipios"]}, key=lambda x: x[1]),
        "tipos": sorted({a["tipo"] for a in avisos if a.get("tipo")}), "rotulos_tipos": ROTULOS,
        "radios": sorted({(e["radio_id"], e["radio_nome"]) for e in envios}, key=lambda x: x[1]),
        "pessoas": sorted({a["usuario"] for a in avisos if a.get("usuario")}),
    }
    return rel


def _filtros_texto(rel: dict) -> str:
    f = dict(rel["filtros"])
    if "municipio" in f:
        f["municipio"] = dict(rel["opcoes"]["municipios"]).get(f["municipio"], f["municipio"])
    if "tipo" in f:
        f["tipo"] = ROTULOS.get(f["tipo"], f["tipo"])
    if "radio" in f:
        f["radio"] = dict((str(k), v) for k, v in rel["opcoes"]["radios"]).get(str(f["radio"]), f["radio"])
    return ", ".join(f"{k}: {v}" for k, v in f.items()) or "sem filtros"


@rotas.get("/api/relatorios/mensal")
def relatorio_mensal(mes: str | None = None, inicio: str | None = None, fim: str | None = None, municipio: str | None = None,
                     tipo: str | None = None, radio: str | None = None, pessoa: str | None = None,
                     u: dict = Depends(exigir("ver_historico"))) -> dict:
    return _mensal(u, mes, inicio, fim, municipio, tipo, radio, pessoa)


def _secoes_mensal(rel: dict) -> list[tuple]:
    r = rel["resumo"]
    sec = [("titulo", "Resumo"), ("numeros", [
        ("Desligamentos programados", str(r["desligamentos"])), ("Cancelados", str(r["cancelados"])),
        ("Avisos (por município)", str(r["avisos"])), ("Comunidades avisadas", str(r["comunidades"])),
        ("UCs no aviso", str(r["ucs"])), ("Com equipamento vital (só a contagem)", str(r["equipamento_vital"])),
        ("Envios às rádios", str(r["envios"])), ("Confirmados pela rádio", str(r["confirmados"])),
        ("Tempo no ar (mensagens enviadas)", _tempo(r["segundos_no_ar"])), ("Custo", _brl(r["custo"])),
        ("Economia calculada (tempo no ar)", _brl(r["economia_calculada"])), ("Economia informada (custo antigo)", _brl(r["economia_informada"])),
        ("Tempo de ar economizado", _tempo(r["tempo_economizado"])),
        ("No prazo", f"{r['no_prazo']} de {r['com_envio']} com envio" + (f" ({r['pct_no_prazo']:.1f}%)".replace(".", ",") if r["pct_no_prazo"] is not None else ""))])]
    if rel.get("comparacao"):
        nomes = {"desligamentos": "Desligamentos", "avisos": "Avisos", "ucs": "UCs", "envios": "Envios", "confirmados": "Confirmados",
                 "segundos_no_ar": "Segundos no ar", "custo": "Custo (R$)", "economia_calculada": "Economia calculada (R$)",
                 "economia_informada": "Economia informada (R$)", "tempo_economizado": "Segundos economizados", "pct_no_prazo": "% no prazo"}
        sec += [("titulo", f"Comparação com {rel['comparacao']['periodo']}"),
                ("tabela", ["Número", "Este período", "Anterior", "Diferença"],
                 [[nomes[k], v["atual"], v["anterior"], v["diferenca"]] for k, v in rel["comparacao"]["numeros"].items()])]
    sec += [("titulo", "Por tipo de desligamento"), ("tabela", ["Tipo", "Desligamentos", "UCs"],
                                                      [[x["rotulo"], x["desligamentos"], x["ucs"]] for x in rel["por_tipo"]]),
            ("titulo", "Por rádio"), ("tabela", ["Rádio", "Envios", "Confirmados", "Tempo no ar", "Custo", "Economia"],
                                      [[x["radio"], x["envios"], x["confirmados"], _tempo(x["segundos"]), _brl(x["custo"]), _brl(x["economia"])]
                                       for x in rel["por_radio"]]),
            ("titulo", "Comunidades mais afetadas"), ("tabela", ["Comunidade", "Distrito", "Município", "Avisos", "UCs"],
                                                      [[x["comunidade"].split(" (")[0], x["distrito"], x["municipio"], x["avisos"], x["ucs"]]
                                                       for x in rel["por_comunidade"]]),
            ("titulo", "Avisos fora do prazo"), ("tabela", ["Aviso", "Desligamento", "Municípios", "Regra", "Atraso"],
                                                 [[x["aviso"], f"{x['data']}, {x['horario']}", x["municipios"], x["regra"], f"{x['atraso_horas']} h"]
                                                  for x in rel["fora_do_prazo"]]),
            ("titulo", "Avisos sem envio registrado"), ("tabela", ["Aviso", "Desligamento", "Municípios"],
                                                        [[x["aviso"], x["data"], x["municipios"]] for x in rel["sem_envio"]]),
            ("titulo", "Como a economia foi calculada")] + [("texto", "- " + t) for t in rel["como_calculado"]]
    sec += [("titulo", "Lista detalhada"), ("tabela", ["Aviso", "Gerado", "Desligamento", "Tipo", "Municípios", "UCs", "Vital", "Rádios",
                                                       "Envios", "Custo", "No prazo", "Pedido por", "Situação"],
                                            [[x["aviso"], datetime.fromisoformat(x["criado_em"]).astimezone(BRASILIA).strftime("%d/%m %H:%M"),
                                              f"{x['data']}, {x['horario']}", x["tipo"], x["municipios"], x["ucs"], x["equipamento_vital"],
                                              x["radios"], f"{x['confirmados']}/{x['envios']}", _brl(x["custo"]),
                                              "-" if x["no_prazo"] is None else "sim" if x["no_prazo"] else "não", x["por"], x["status"]]
                                             for x in rel["lista"]])]
    return sec


@rotas.get("/api/relatorios/mensal.pdf")
def relatorio_mensal_pdf(mes: str | None = None, inicio: str | None = None, fim: str | None = None, municipio: str | None = None,
                         tipo: str | None = None, radio: str | None = None, pessoa: str | None = None,
                         u: dict = Depends(exigir("ver_historico"))) -> Response:
    rel = _mensal(u, mes, inicio, fim, municipio, tipo, radio, pessoa)
    codigo = _registrar(u, "gerou relatório do período (PDF)", f"{rel['periodo']['rotulo']}; {_filtros_texto(rel)}")
    pdf = pdf_relatorio.documento(f"Relatório de avisos - {rel['periodo']['rotulo']}", f"{u.get('empresa_nome') or ''} - {_filtros_texto(rel)}",
                                  _quem(u), codigo, _secoes_mensal(rel), AVISO_FICTICIO, datetime.now(BRASILIA), paisagem=True)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="farol-relatorio-{rel["periodo"]["inicio"][:7]}.pdf"', "X-Codigo": codigo})


@rotas.get("/api/relatorios/mensal.csv")
def relatorio_mensal_csv(mes: str | None = None, inicio: str | None = None, fim: str | None = None, municipio: str | None = None,
                         tipo: str | None = None, radio: str | None = None, pessoa: str | None = None,
                         u: dict = Depends(exigir("ver_historico"))) -> Response:
    rel = _mensal(u, mes, inicio, fim, municipio, tipo, radio, pessoa)
    codigo = _registrar(u, "gerou relatório do período (CSV)", f"{rel['periodo']['rotulo']}; {_filtros_texto(rel)}")
    return Response("﻿" + R.mensal_csv(rel, _quem(u), codigo), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="farol-relatorio-{rel["periodo"]["inicio"][:7]}.csv"', "X-Codigo": codigo})


# ---------- Comprovante de um aviso ----------
def _comprovante(id_: int, u: dict) -> dict:
    a = banco_acesso.aviso(id_, u["empresa_id"])
    if not a:
        raise HTTPException(404, "Aviso não encontrado nesta empresa.")
    return R.comprovante(a, banco.envios(u["empresa_id"], [id_]), DIST.prazo_legal_horas, DIST.prazo_vital_dias_uteis)


@rotas.get("/api/historico/{id_}/comprovante")
def comprovante(id_: int, u: dict = Depends(exigir("ver_historico"))) -> dict:
    return _comprovante(id_, u)


@rotas.get("/api/historico/{id_}/comprovante.pdf")
def comprovante_pdf(id_: int, u: dict = Depends(exigir("ver_historico"))) -> Response:
    c = _comprovante(id_, u)
    codigo = _registrar(u, "gerou comprovante do aviso (PDF)", f"aviso {id_} ({c['codigo']})")
    criado = datetime.fromisoformat(c["criado_em"]).astimezone(BRASILIA)
    p = c["prazo"]
    sec = [("titulo", "O desligamento"), ("numeros", [
        ("Aviso", f"nº {c['aviso']} - código {c['codigo'] or '-'}"), ("Situação", c["status"]),
        ("Solicitado por", f"{c['por']} ({PERFIS.get(c['perfil'], '')})"), ("Quando", f"{criado:%d/%m/%Y às %H:%M}"),
        ("Desligamento", f"{c['data']}, {c['horario']}"), ("Tipo", f"{c['tipo']} ({c['motivo']})"),
        ("UCs no aviso", str(c["ucs"])), ("Com equipamento vital (só a contagem)", str(c["equipamento_vital"])),
        ("Prazo", f"{p['regra']}: " + ("sem envio registrado" if p["no_prazo"] is None else "no prazo" if p["no_prazo"] else f"fora do prazo ({p['atraso_horas']} h)")),
        ("Custo", _brl(c["custo"])), ("Economia calculada", _brl(c["economia_calculada"])), ("Economia informada", _brl(c["economia_informada"]))])]
    for m in c["municipios"]:
        sec += [("titulo", f"{m['nome']}: {m['ucs']} UCs, {m['equipamento_vital']} com equipamento vital"), ("texto", ", ".join(m["comunidades"]))]
    sec += [("titulo", "Envios às rádios"), ("tabela", ["Rádio", "Canal", "Quando", "Situação", "Confirmado em", "Valor", "Custo", "Economia", "Por"],
                                              [[e["radio"], e["canal"], datetime.fromisoformat(e["quando"]).astimezone(BRASILIA).strftime("%d/%m %H:%M"),
                                                STATUS.get(e["status"], e["status"]),
                                                datetime.fromisoformat(e["confirmado_em"]).astimezone(BRASILIA).strftime("%d/%m %H:%M") if e["confirmado_em"] else "-",
                                                _brl(e["valor"]), _brl(e["custo"]),
                                                f"{_brl(e['economia'])} ({e['economia_tipo']})" if e["economia"] is not None else "-", e["por"]]
                                               for e in c["envios"]], (3.2, 1.2, 1.4, 1.5, 1.4, 1.3, 1.3, 2, 1.8))]
    pdf = pdf_relatorio.documento(f"Comprovante do aviso nº {c['aviso']}", f"{u.get('empresa_nome') or ''} - desligamento de {c['data']}, {c['horario']}",
                                  _quem(u), codigo, sec, AVISO_FICTICIO, datetime.now(BRASILIA))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="farol-comprovante-aviso-{id_}.pdf"', "X-Codigo": codigo})


# ---------- Auditoria da empresa (Admin da empresa) e acessos de todas (Admin do Farol) ----------
def _linhas(rs: list[dict]) -> list[dict]:
    return [{"quando": r["quando"].astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M:%S"), "usuario": r["usuario"],
             "perfil": PERFIS.get(r["perfil"], r["perfil"] or ""), "empresa": r["empresa"], "acao": r["acao"], "detalhe": r["detalhe"],
             "codigo": codigo_verificacao(r["hash"]) if r["hash"] else None} for r in rs]


def _auditoria(u: dict, geral: bool, mes, inicio, fim, pessoa, empresa, so_acessos: bool) -> dict:
    i, f, _ = _periodo(mes, inicio, fim)
    rs = banco.registros(None if geral else u["empresa_id"], i, f, pessoa=pessoa or None,
                         acoes=ACESSOS if so_acessos else None, empresa_sigla=(empresa or None) if geral else None)
    linhas = _linhas(rs)
    return {"periodo": {"inicio": i.isoformat(), "fim": f.isoformat(), "rotulo": R.rotulo_periodo(i, f)}, "linhas": linhas,
            "total": len(linhas), "pessoas": sorted({x["usuario"] for x in linhas if x["usuario"]}),
            "filtros": {k: v for k, v in {"pessoa": pessoa, "empresa": empresa if geral else None, "só acessos": "sim" if so_acessos else None}.items() if v}}


def _exportar_auditoria(u: dict, geral: bool, formato: str, **kw) -> Response:
    d = _auditoria(u, geral, **kw)
    titulo = ("Auditoria geral de acessos" if geral else "Relatório de auditoria") + f" - {d['periodo']['rotulo']}"
    filtros = ", ".join(f"{k}: {v}" for k, v in d["filtros"].items()) or "sem filtros"
    codigo = _registrar(u, f"gerou {'auditoria geral de acessos' if geral else 'relatório de auditoria'} ({formato.upper()})",
                        f"{d['periodo']['rotulo']}; {filtros}; {d['total']} linhas")
    nome = f"farol-{'acessos' if geral else 'auditoria'}-{d['periodo']['inicio'][:7]}.{formato}"
    if formato == "csv":
        return Response("﻿" + R.auditoria_csv(d["linhas"], titulo, _quem(u), codigo), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"', "X-Codigo": codigo})
    sec = [("texto", f"{d['total']} linha(s). Nada é apagado nem alterado na auditoria; cada linha guarda o código da anterior."),
           ("tabela", ["Quando", "Quem", "Perfil", "Empresa", "O quê", "Detalhe", "Código"],
            [[x["quando"], x["usuario"] or "-", x["perfil"], x["empresa"] or "-", x["acao"], x["detalhe"], x["codigo"]] for x in d["linhas"]])]
    pdf = pdf_relatorio.documento(titulo, f"{'Todas as empresas' if geral else u.get('empresa_nome') or ''} - {filtros}", _quem(u), codigo, sec,
                                  AVISO_FICTICIO, datetime.now(BRASILIA), paisagem=True)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nome}"', "X-Codigo": codigo})


@rotas.get("/api/relatorios/auditoria")
def relatorio_auditoria(mes: str | None = None, inicio: str | None = None, fim: str | None = None, pessoa: str | None = None,
                        so_acessos: bool = False, u: dict = Depends(exigir("relatorio_auditoria"))) -> dict:
    return _auditoria(u, False, mes, inicio, fim, pessoa, None, so_acessos)


@rotas.get("/api/relatorios/auditoria.{formato}")
def relatorio_auditoria_arquivo(formato: str, mes: str | None = None, inicio: str | None = None, fim: str | None = None,
                                pessoa: str | None = None, so_acessos: bool = False,
                                u: dict = Depends(exigir("relatorio_auditoria"))) -> Response:
    if formato not in ("pdf", "csv"):
        raise HTTPException(404, "Formato: pdf ou csv.")
    return _exportar_auditoria(u, False, formato, mes=mes, inicio=inicio, fim=fim, pessoa=pessoa, empresa=None, so_acessos=so_acessos)


@rotas.get("/api/relatorios/acessos")
def relatorio_acessos(mes: str | None = None, inicio: str | None = None, fim: str | None = None, pessoa: str | None = None,
                      empresa: str | None = Query(None, max_length=10), so_acessos: bool = True,
                      u: dict = Depends(exigir("auditoria_geral"))) -> dict:
    return _auditoria(u, True, mes, inicio, fim, pessoa, empresa, so_acessos)


@rotas.get("/api/relatorios/acessos.{formato}")
def relatorio_acessos_arquivo(formato: str, mes: str | None = None, inicio: str | None = None, fim: str | None = None,
                              pessoa: str | None = None, empresa: str | None = Query(None, max_length=10), so_acessos: bool = True,
                              u: dict = Depends(exigir("auditoria_geral"))) -> Response:
    if formato not in ("pdf", "csv"):
        raise HTTPException(404, "Formato: pdf ou csv.")
    return _exportar_auditoria(u, True, formato, mes=mes, inicio=inicio, fim=fim, pessoa=pessoa, empresa=empresa, so_acessos=so_acessos)


def painel_do_mes(empresa_id: int, hoje: date) -> dict:
    """Os números do mês corrente para o dashboard: gasto, economizado, avisos e % no prazo."""
    i, f = R.periodo_do_mes(f"{hoje:%Y-%m}")
    avisos = banco.avisos(empresa_id, i, f)
    r = R.mensal(avisos, banco.envios(empresa_id, [a["id"] for a in avisos]), i, f, {}, DIST.prazo_legal_horas,
                 DIST.prazo_vital_dias_uteis)["resumo"]
    return {"mes": R.rotulo_periodo(i, f), "gasto": r["custo"], "economia_calculada": r["economia_calculada"],
            "economia_informada": r["economia_informada"], "tempo_economizado": r["tempo_economizado"], "desligamentos": r["desligamentos"],
            "envios": r["envios"], "confirmados": r["confirmados"], "pct_no_prazo": r["pct_no_prazo"], "com_envio": r["com_envio"]}

