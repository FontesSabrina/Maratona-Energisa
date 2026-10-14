# Roda todos os testes do Farol e mostra uma tabela no fim (nome, verificações, resultado, tempo).
# Uso (na raiz, com o Postgres local no ar):  powershell -ExecutionPolicy Bypass -File testes\rodar_testes.ps1
# Opções: -Rapido (sem o navegador nem o --so-algoritmo) e -SemAlgoritmo (sem o --so-algoritmo).
param([switch]$Rapido, [switch]$SemAlgoritmo)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $env:PATH = "$env:APPDATA\Python\Python312\Scripts;$env:PATH"   # uv instalado pelo pip --user
}

$testes = @(
    @{ Nome = "Coordenadas (tradutor)";        Cmd = "uv run python -W ignore testes/planilha/teste_coordenadas.py" },
    @{ Nome = "Tradutor da planilha";          Cmd = "uv run python -W ignore testes/planilha/teste_tradutor.py" },
    @{ Nome = "Dupla conferência";             Cmd = "uv run python -W ignore testes/planilha/teste_conferencia.py" },
    @{ Nome = "Travas e pacote assinado";      Cmd = "uv run python -W ignore testes/planilha/teste_travas.py" },
    @{ Nome = "Planilhas de demonstração";     Cmd = "uv run python -W ignore testes/planilha/teste_demo.py" },
    @{ Nome = "Planilha (endereço, sinônimos)"; Cmd = "uv run python -W ignore testes/nucleo/teste_planilha.py" },
    @{ Nome = "Proxy (IP e https)";            Cmd = "uv run python -W ignore testes/api/teste_proxy.py" },
    @{ Nome = "Leitura segura (zip, macro)";   Cmd = "uv run python -W ignore testes/api/teste_leitura.py" },
    @{ Nome = "Senhas (Argon2id)";             Cmd = "uv run python -W ignore testes/api/teste_senhas.py" },
    @{ Nome = "API";                           Cmd = "uv run python -W ignore testes/api/teste_api.py" },
    @{ Nome = "Acesso (login, perfis)";        Cmd = "uv run python -W ignore testes/api/teste_acesso.py" },
    @{ Nome = "Matriz rota x perfil";          Cmd = "uv run python -W ignore testes/api/teste_matriz.py" },
    @{ Nome = "Auditoria encadeada";           Cmd = "uv run python -W ignore testes/api/teste_auditoria.py" },
    @{ Nome = "Rádio, envio e cofre (Mailpit)"; Cmd = "uv run python -W ignore testes/api/teste_radio.py" },
    @{ Nome = "Relatórios e prazo";            Cmd = "uv run python -W ignore testes/api/teste_relatorios.py" },
    @{ Nome = "Áudio (MP3)";                   Cmd = "uv run python -W ignore testes/api/teste_audio.py" },
    @{ Nome = "Admin (modelo, Node)";          Cmd = "node testes/admin/teste_modelo.mjs" },
    @{ Nome = "Minimização Leopoldina";        Cmd = "uv run python -m comunidades.validacao.minimizacao" },
    @{ Nome = "Minimização Muriaé";            Cmd = "`$env:FAROL_DISTRIBUIDORA='distribuidoras/demo-muriae.toml'; uv run python -m comunidades.validacao.minimizacao; Remove-Item Env:FAROL_DISTRIBUIDORA" }
)
if (-not $Rapido) {
    $testes += @{ Nome = "Tela do app (navegador)"; Cmd = "uv run python testes/navegador/rodar_teste_app.py" }
    if (-not $SemAlgoritmo) {
        $testes += @{ Nome = "Algoritmo (--so-algoritmo)"; Cmd = "uv run comunidades --so-algoritmo" }
    }
}

$linhas = @()
foreach ($t in $testes) {
    Write-Host "== $($t.Nome)" -ForegroundColor Cyan
    $inicio = Get-Date
    $saida = Invoke-Expression "$($t.Cmd) 2>&1" | ForEach-Object { "$_" }
    $codigo = $LASTEXITCODE
    $tempo = [int]((Get-Date) - $inicio).TotalSeconds
    $falhas = @($saida | Where-Object { $_ -match "^FALHA" })
    $falhas | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
    $conta = ($saida | Select-String -Pattern "(\d+) de (\d+) verifica" | Select-Object -Last 1)
    $verif = if ($conta) { "$($conta.Matches[0].Groups[1].Value)/$($conta.Matches[0].Groups[2].Value)" } else { "-" }
    if ($t.Nome -like "Minimização*") {
        $ok = ($codigo -eq 0) -and ($saida -match "Nenhum titular")
        $verif = if ($ok) { "0 ocorrências" } else { "OCORRÊNCIA" }
    } elseif ($t.Nome -like "Algoritmo*") {
        $m = ($saida | Select-String "Cenários:" | Select-Object -Last 1)
        $ok = ($codigo -eq 0) -and ("$m" -match "cobertura média 88\.3% \| precisão média 95\.0% \| aviso 44s -> 14s")
        $verif = if ($m) { ("$m").Trim() } else { "-" }
    } else {
        $ok = ($codigo -eq 0) -and ($falhas.Count -eq 0)
    }
    $linhas += [pscustomobject]@{ Teste = $t.Nome; Verificacoes = $verif; Resultado = $(if ($ok) { "OK" } else { "FALHOU" }); Segundos = $tempo }
}

Write-Host ""
$linhas | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
$ruins = @($linhas | Where-Object { $_.Resultado -ne "OK" })
if ($ruins.Count) {
    Write-Host "$($ruins.Count) teste(s) falharam." -ForegroundColor Red
    exit 1
}
Write-Host "Todos os $($linhas.Count) testes passaram." -ForegroundColor Green
exit 0
