"""Listas fechadas do tradutor da planilha: motivo de rejeição, correção feita e aviso de cada linha.

O JSON da planilha guarda só o código (o valor do Enum), nunca texto livre; a tela e o relatório
mostram o texto de TEXTOS. Um código novo entra aqui, com o seu texto, e em nenhum outro lugar.
"""

from enum import Enum


class Motivo(str, Enum):
    """Por que a linha foi rejeitada."""
    # coordenada (nucleo/coordenadas.py)
    COORD_VAZIA = "coordenada_vazia"
    COORD_INCOMPLETA = "coordenada_incompleta"
    COORD_SEM_NUMERO = "coordenada_sem_numero"
    COORD_FORMATO = "coordenada_formato"
    COORD_DATA = "coordenada_data"
    COORD_FORMULA = "coordenada_formula_sem_valor"
    COORD_NAO_FINITA = "coordenada_nao_finita"
    COORD_LIMITES = "coordenada_fora_dos_limites"
    FORA_DA_CONCESSAO = "fora_da_concessao"
    CORRECAO_AMBIGUA = "correcao_ambigua"


class Correcao(str, Enum):
    """O que foi corrigido numa linha "corrigida" (só quando o ponto corrigido cai na concessão)."""
    TROCA = "latitude_e_longitude_trocadas"
    SINAL_LAT = "sinal_da_latitude"
    SINAL_LON = "sinal_da_longitude"
    SINAL_AMBOS = "sinal_da_latitude_e_da_longitude"
    TROCA_E_SINAL = "trocadas_e_sinal"
    UTM_TROCADO = "utm_x_e_y_trocados"


class Aviso(str, Enum):
    """Alerta que não rejeita a linha."""
    POUCAS_CASAS = "menos_de_4_casas_decimais"


TEXTOS = {
    Motivo.COORD_VAZIA: "sem coordenada",
    Motivo.COORD_INCOMPLETA: "só a latitude ou só a longitude",
    Motivo.COORD_SEM_NUMERO: "coordenada sem número",
    Motivo.COORD_FORMATO: "coordenada num formato não reconhecido",
    Motivo.COORD_DATA: "coordenada numa célula de data",
    Motivo.COORD_FORMULA: "fórmula sem valor guardado na coordenada",
    Motivo.COORD_NAO_FINITA: "coordenada inválida (NaN ou infinito)",
    Motivo.COORD_LIMITES: "coordenada fora dos limites (latitude de -90 a 90, longitude de -180 a 180)",
    Motivo.FORA_DA_CONCESSAO: "fora da área de concessão",
    Motivo.CORRECAO_AMBIGUA: "mais de uma correção possível: nada foi adivinhado",
    Correcao.TROCA: "latitude e longitude estavam trocadas",
    Correcao.SINAL_LAT: "faltava o sinal negativo da latitude",
    Correcao.SINAL_LON: "faltava o sinal negativo da longitude",
    Correcao.SINAL_AMBOS: "faltava o sinal negativo da latitude e da longitude",
    Correcao.TROCA_E_SINAL: "latitude e longitude trocadas e sem o sinal negativo",
    Correcao.UTM_TROCADO: "coordenadas UTM com X e Y trocados",
    Aviso.POUCAS_CASAS: "coordenada com menos de 4 casas decimais (cerca de 11 m de precisão ou pior)",
}


class FormulaSemValor:
    """Célula com fórmula e sem o valor calculado guardado no arquivo (quem lê o arquivo a marca assim)."""

    def __repr__(self) -> str:
        return "FormulaSemValor()"


FORMULA_SEM_VALOR = FormulaSemValor()
