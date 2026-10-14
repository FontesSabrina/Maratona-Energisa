"""O que as rotas da API compartilham: a distribuidora, o horário de Brasília, o áudio e a configuração
efetiva de cada empresa (a do banco, com os padrões da distribuidora no que faltar)."""

import os
from datetime import timedelta, timezone

from fastapi import HTTPException

from .. import distribuidora as dist_
from ..banco import acesso as banco_acesso
from ..banco import radios as banco_radios
from ..nucleo import mensagem
from ..nucleo.desligamento import PALAVRAS_POR_SEGUNDO

DIST = dist_.carregar()
# FAROL_AUDIO=0 desliga o áudio do aviso (o plano gratuito do Render não tem memória para a voz)
AUDIO = os.environ.get("FAROL_AUDIO", "1") != "0"
AVISO_FICTICIO = ("Rede elétrica e clientes fictícios nesta demonstração; território, endereços e "
                  "comunidades reais (IBGE, Censo 2022).")
BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
MAX_TEXTO = 40                            # data e horário: o que vai no aviso, digitado pelo operador


def texto_do_aviso(nome: str, v: str) -> str:
    v = " ".join(str(v).split())
    if not v or len(v) > MAX_TEXTO:
        raise HTTPException(422, f"{nome}: informe de 1 a {MAX_TEXTO} caracteres.")
    return v


def segundos(texto: str) -> int:
    """Tempo no ar do texto (a mesma conta do aviso: palavras / palavras por segundo)."""
    return round(len(str(texto).split()) / PALAVRAS_POR_SEGUNDO)


def config_empresa(empresa_id: int | None) -> dict:
    """A configuração que vale para a empresa: o que o Admin da empresa gravou e, no resto, os padrões."""
    c = banco_radios.config(empresa_id) if empresa_id else {}
    emp = banco_acesso.empresa(empresa_id) if empresa_id else None
    escolher = lambda campo, padrao: c.get(campo) if c.get(campo) is not None else padrao
    return {
        "modelo_mensagem": escolher("modelo_mensagem", mensagem.PADRAO),
        "nome_mensagem": escolher("nome_mensagem", (emp or {}).get("nome") or DIST.nome),
        "telefone": escolher("telefone", DIST.telefone),
        "limite_rejeicao": float(escolher("limite_rejeicao", DIST.planilha.limite_rejeitadas)),
        "epsg_utm": int(escolher("epsg_utm", DIST.planilha.epsg_utm)),
        "antecedencia_dias": int(escolher("antecedencia_dias", DIST.prazo_interno_dias)),
        "padroes": not c,
    }
