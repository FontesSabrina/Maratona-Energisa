"""Teste da leitura do arquivo enviado (api/leitura.py): zip bomb no .xlsx, sem banco.

Confere:
- um .xlsx normal e um do tamanho máximo (50.000 linhas) passam e são lidos;
- recusados antes do openpyxl: conteúdo descompactado acima de 100 MB, compactação fora do normal
  (razão acima de 200), arquivos internos demais;
- um .xlsx que declara no índice um tamanho menor que o real não descompacta além do declarado
  (o zipfile recusa), então os tamanhos declarados limitam a memória;
- .csv continua igual.

Uso (na raiz): uv run python -W ignore testes/api/teste_leitura.py
"""

import io
import struct
import sys
import zipfile

import pandas as pd

from comunidades.api import leitura
from comunidades.nucleo.planilha import PlanilhaInvalida

resultados = []


def conferir(nome, ok, extra=""):
    resultados.append(("OK  " if ok else "FALHA", nome, extra))


def xlsx(t: pd.DataFrame) -> bytes:
    b = io.BytesIO()
    t.to_excel(b, index=False)
    return b.getvalue()


def zip_com(itens: dict[str, bytes]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, dados in itens.items():
            z.writestr(nome, dados)
    return b.getvalue()


def recusa(conteudo: bytes) -> str | None:
    """A mensagem da recusa (None: o arquivo foi aceito)."""
    try:
        leitura.ler(conteudo)
    except PlanilhaInvalida as e:
        return str(e)
    return None


normal = pd.DataFrame({"uc": ["1", "2"], "latitude": ["-21,53", "-21,54"], "longitude": ["-42,64", "-42,65"]})
t = leitura.ler(xlsx(normal))
conferir(".xlsx normal é lido", t.to_dict("list") == normal.to_dict("list"), str(t.head()))

n = 50_000
grande = pd.DataFrame({"uc": [f"{i:010d}" for i in range(n)], "latitude": [f"-21,{5300 + i % 900}" for i in range(n)],
                       "longitude": [f"-42,{6400 + i % 700}" for i in range(n)], "equipamento_vital": ["não"] * n,
                       "classe": ["residencial"] * n, "endereco": [f"Rua {i % 300}, {i % 999}" for i in range(n)]})
b = xlsx(grande)
with zipfile.ZipFile(io.BytesIO(b)) as z:
    total = sum(i.file_size for i in z.infolist())
    razao = max(i.file_size / max(i.compress_size, 1) for i in z.infolist())
conferir(f".xlsx de {n:,} linhas passa".replace(",", ".") + f" (folga: {total / 1e6:.0f} MB descompactado, razão máx. {razao:.0f})",
         recusa(b) is None and len(leitura.ler(b)) == n, recusa(b))

# 150 MB de zeros: ~150 KB compactado (passa do total e da razão)
bomba = zip_com({"[Content_Types].xml": b"<Types/>", "xl/worksheets/sheet1.xml": b"\0" * (150 * 1024 * 1024)})
msg = recusa(bomba)
conferir(f"zip bomb ({len(bomba) // 1024} KB que viram 150 MB) recusado antes do openpyxl", msg is not None and "100 MB" in msg, msg)

# 30 MB de zeros: cabe no total, mas a razão (~1000) não
razao_alta = zip_com({"[Content_Types].xml": b"<Types/>", "xl/worksheets/sheet1.xml": b"\0" * (30 * 1024 * 1024)})
msg = recusa(razao_alta)
conferir("compactação fora do normal (razão ~1000) recusada", msg is not None and "compactação" in msg, msg)

muitos = zip_com({f"xl/x{i}.xml": b"<a/>" for i in range(leitura.MAX_ENTRADAS + 1)})
msg = recusa(muitos)
conferir(f"mais de {leitura.MAX_ENTRADAS} arquivos internos recusado", msg is not None and "arquivos internos" in msg, msg)

# índice mentiroso: declara 1.000 bytes para um arquivo de 5 MB (de texto variado, razão normal)
real = "".join(f"<c r='A{i}'><v>{i * 7919 % 100003}</v></c>" for i in range(200_000)).encode()[:5 * 1024 * 1024]
b = bytearray(zip_com({"xl/worksheets/sheet1.xml": real}))
cd = b.find(b"PK\x01\x02")
struct.pack_into("<I", b, cd + 24, 1000)        # tamanho descompactado no índice central
leu = None
try:
    with zipfile.ZipFile(io.BytesIO(bytes(b))) as z:
        leu = len(z.read("xl/worksheets/sheet1.xml"))
except (zipfile.BadZipFile, OSError) as e:
    leu = f"recusado: {type(e).__name__}"
conferir("tamanho declarado menor que o real: o zipfile não passa do declarado", leu == "recusado: BadZipFile" or
         (isinstance(leu, int) and leu <= 1000), leu)
conferir("e a planilha com índice mentiroso é recusada", recusa(bytes(b)) is not None, recusa(bytes(b)))

conferir(".csv continua sendo lido", len(leitura.ler("uc;latitude;longitude\n1;-21,5;-42,6\n".encode())) == 1)

for st, nome, extra in resultados:
    print(st, nome, f"-> {extra}" if st != "OK  " else "")
falhas = sum(1 for r in resultados if r[0] != "OK  ")
print(f"\n{len(resultados) - falhas} de {len(resultados)} verificações OK")
sys.exit(1 if falhas else 0)
