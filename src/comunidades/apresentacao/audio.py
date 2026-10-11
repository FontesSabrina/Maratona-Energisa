"""Áudio do aviso para a rádio: voz sintetizada offline (Piper) e MP3.

- Voz: Piper (piper-tts, GPL-3.0) com as vozes pt-BR de qualidade média do repositório oficial
  rhasspy/piper-voices (dados de treino CC0). Roda no servidor, sem internet e sem chave: o texto
  do aviso não sai daqui. A voz é baixada uma vez para data/raw/vozes/ e conferida pelo MD5 publicado.
- MP3: 128 kbps, mono, 44,1 kHz, o padrão das rádios (lameenc, o LAME, LGPL). A voz sai a 22,05 kHz e o
  LAME converte; sem isso o arquivo seria MPEG-2, que alguns sistemas de automação de rádio recusam.
- Antes de falar, o texto passa por nucleo/locucao.py ("8h às 14h" -> "8 horas às 14 horas").
- Isolado neste módulo: trocar de motor (um serviço de nuvem, por exemplo) não mexe no resto.

A voz padrão é FAROL_VOZ (padrão pt_BR-faber-medium). Só português por enquanto.
Uso (amostras das vozes): uv run python -m comunidades.apresentacao.audio
"""

import functools
import hashlib
import json
import os
import shutil
import threading
import urllib.request
from pathlib import Path

import lameenc

from .. import config as C
from ..nucleo.locucao import texto_para_fala

REPOSITORIO = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOZES = {  # nome -> caminho no repositório (todas pt-BR, qualidade média, dados de treino CC0)
    "pt_BR-faber-medium": "pt/pt_BR/faber/medium",
    "pt_BR-cadu-medium": "pt/pt_BR/cadu/medium",
    "pt_BR-jeff-medium": "pt/pt_BR/jeff/medium",
}
VOZ_PADRAO = os.environ.get("FAROL_VOZ") or "pt_BR-faber-medium"
PASTA = C.RAW / "vozes"
KBPS = 128
TAXA_SAIDA = 44_100
MAX_CARACTERES = 3000
MAX_CARACTERES_COMPARATIVO = 30_000  # o aviso de hoje (fazenda a fazenda) no comparativo
_trava = threading.Lock()   # o modelo é um só por processo; uma síntese por vez


def _baixar(url: str, destino: Path) -> None:
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.replace(destino)


@functools.lru_cache(maxsize=1)
def _catalogo() -> dict:
    arq = PASTA / "voices.json"
    if not arq.exists():
        PASTA.mkdir(parents=True, exist_ok=True)
        _baixar(f"{REPOSITORIO}/voices.json", arq)
    return json.loads(arq.read_text(encoding="utf-8"))


def garantir_voz(nome: str = VOZ_PADRAO) -> Path:
    """Baixa o modelo (.onnx e .onnx.json) se faltar e confere o MD5 de cada arquivo com o catálogo."""
    if nome not in VOZES:
        raise ValueError(f"voz desconhecida: {nome} (use uma de {', '.join(VOZES)})")
    arquivos = _catalogo()[nome]["files"]
    for sufixo in (".onnx", ".onnx.json"):
        caminho = f"{VOZES[nome]}/{nome}{sufixo}"
        destino = PASTA / f"{nome}{sufixo}"
        if not destino.exists():
            print(f"  baixando a voz {destino.name}...", flush=True)
            _baixar(f"{REPOSITORIO}/{caminho}", destino)
        md5 = hashlib.md5(destino.read_bytes()).hexdigest()
        if md5 != arquivos[caminho]["md5_digest"]:
            destino.unlink()
            raise RuntimeError(f"{destino.name}: MD5 não confere com o catálogo do Piper (arquivo apagado; baixe de novo)")
    return PASTA / f"{nome}.onnx"


@functools.lru_cache(maxsize=3)
def _voz(nome: str):
    from piper import PiperVoice  # importa só quando o áudio é pedido (o modelo leva ~1 s para carregar)
    return PiperVoice.load(str(garantir_voz(nome)))


def mp3(texto: str, idioma: str = "pt-BR", voz: str = VOZ_PADRAO, max_caracteres: int = MAX_CARACTERES) -> tuple[bytes, float]:
    """(MP3, duração em segundos) do texto falado."""
    if idioma != "pt-BR":
        raise ValueError("Por enquanto o áudio é só em português.")
    fala = texto_para_fala(texto)
    if not fala or len(fala) > max_caracteres:
        raise ValueError(f"O texto do áudio tem de ter de 1 a {max_caracteres:,} caracteres.".replace(",", "."))
    with _trava:
        v = _voz(voz)
        pedacos = list(v.synthesize(fala))
    taxa = pedacos[0].sample_rate
    pcm = b"".join(p.audio_int16_bytes for p in pedacos)
    enc = lameenc.Encoder()
    enc.set_bit_rate(KBPS)
    enc.set_in_sample_rate(taxa)
    enc.set_out_sample_rate(TAXA_SAIDA)
    enc.set_channels(1)
    enc.set_quality(2)  # 2 = alta qualidade
    dados = bytes(enc.encode(pcm)) + bytes(enc.flush())
    return dados, len(pcm) / 2 / taxa


if __name__ == "__main__":
    exemplo = ("Atenção, moradores de Graminha, Boa Sorte e Piacatuba, e de parte de Tomé Nogueira, em Leopoldina "
               "(distritos Piacatuba e Sede): no dia 20/11, das 8h às 14h30, haverá desligamento programado de energia "
               "para manutenção na rede. Programe-se!")
    saida = C.SAIDA / "audio_amostras"
    saida.mkdir(parents=True, exist_ok=True)
    print(f"Texto falado: {texto_para_fala(exemplo)}")
    for nome in VOZES:
        dados, seg = mp3(exemplo, voz=nome)
        (saida / f"{nome}.mp3").write_bytes(dados)
        print(f"{nome}: {seg:.1f} s, {len(dados) / 1024:.0f} KB -> {saida / (nome + '.mp3')}")
