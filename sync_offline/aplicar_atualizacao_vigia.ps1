# Aplica o pacote offline VIGIA (4 categorias + fontes DW/IndicaSUS) sobre a pasta do projeto.
# Uso (PowerShell, na pasta do projeto OU apontando -Destino):
#   .\aplicar_atualizacao_vigia.ps1
#   .\aplicar_atualizacao_vigia.ps1 -Destino "C:\Users\...\Monitoramento ondas de calor"
#
# O script:
# 1) faz backup timestampado dos arquivos que serão substituídos
# 2) copia os arquivos deste pacote por cima da instalação local
# 3) NÃO altera o seu .env (só mostra checklist)

param(
    [string]$Destino = ""
)

$ErrorActionPreference = "Stop"
$PacoteRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ([string]::IsNullOrWhiteSpace($Destino)) {
    # Se o script estiver dentro de sync_offline\ no projeto, sobe um nível.
    if ((Split-Path -Leaf $PacoteRoot) -eq "sync_offline") {
        $Destino = Split-Path -Parent $PacoteRoot
    } else {
        $Destino = (Get-Location).Path
    }
}

if (-not (Test-Path (Join-Path $Destino "sisclima"))) {
    Write-Error "Destino inválido (não achei pasta sisclima): $Destino"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $Destino "backup_pre_vigia4_$stamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

$relPaths = @(
    "atualizar_ocupacao_indicasus.py",
    "validar_fontes_dw.py",
    "preview_alerta_vigia.py",
    "pages\12_Alertas_Agendados_VIGIA.py",
    "sisclima\pipeline.py",
    "sisclima\alerts\vigia_alerts.py",
    "sisclima\alerts\notifier.py",
    "sisclima\alerts\change_detector.py",
    "sisclima\ingestion\sqlserver.py",
    "sisclima\ingestion\pressao_sources.py",
    "sisclima\ingestion\indicasus_ocupacao.py",
    "sisclima\ingestion\dw_sources.py",
    "sisclima\ingestion\sivep_local.py",
    "sisclima\engines\cnes_ops.py",
    "sisclima\engines\epidemiology.py",
    "sisclima\engines\resilience.py",
    "sisclima\core\config.py",
    "sisclima\public\exporter.py"
)

Write-Host "=== Atualização offline VIGIA 4 categorias ===" -ForegroundColor Cyan
Write-Host "Pacote : $PacoteRoot"
Write-Host "Destino: $Destino"
Write-Host "Backup : $BackupDir"
Write-Host ""

foreach ($rel in $relPaths) {
    $src = Join-Path $PacoteRoot $rel
    $dst = Join-Path $Destino $rel
    if (-not (Test-Path $src)) {
        Write-Warning "Arquivo ausente no pacote: $rel"
        continue
    }
    $dstDir = Split-Path -Parent $dst
    if (-not (Test-Path $dstDir)) {
        New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
    }
    if (Test-Path $dst) {
        $bak = Join-Path $BackupDir $rel
        $bakDir = Split-Path -Parent $bak
        New-Item -ItemType Directory -Path $bakDir -Force | Out-Null
        Copy-Item -LiteralPath $dst -Destination $bak -Force
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host "OK  $rel"
}

# SQL: copia todos do pacote
$sqlSrc = Join-Path $PacoteRoot "sql"
$sqlDst = Join-Path $Destino "sql"
if (Test-Path $sqlSrc) {
    if (-not (Test-Path $sqlDst)) { New-Item -ItemType Directory -Path $sqlDst -Force | Out-Null }
    Get-ChildItem -Path $sqlSrc -Filter *.sql | ForEach-Object {
        $target = Join-Path $sqlDst $_.Name
        if (Test-Path $target) {
            $bak = Join-Path $BackupDir ("sql\" + $_.Name)
            New-Item -ItemType Directory -Path (Split-Path -Parent $bak) -Force | Out-Null
            Copy-Item -LiteralPath $target -Destination $bak -Force
        }
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        Write-Host "OK  sql\$($_.Name)"
    }
}

# Docs de referência (não sobrescrevem obrigatoriamente o fluxo)
$docsSrc = Join-Path $PacoteRoot "docs"
$docsDst = Join-Path $Destino "docs"
if (Test-Path $docsSrc) {
    if (-not (Test-Path $docsDst)) { New-Item -ItemType Directory -Path $docsDst -Force | Out-Null }
    Get-ChildItem -Path $docsSrc -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $docsDst $_.Name) -Force
        Write-Host "OK  docs\$($_.Name)"
    }
}

# .env.producao.example na raiz
$envEx = Join-Path $PacoteRoot ".env.producao.example"
if (Test-Path $envEx) {
    Copy-Item -LiteralPath $envEx -Destination (Join-Path $Destino ".env.producao.example") -Force
    Write-Host "OK  .env.producao.example"
}

Write-Host ""
Write-Host "=== Verificação rápida ===" -ForegroundColor Cyan
$vigia = Join-Path $Destino "sisclima\alerts\vigia_alerts.py"
$hit = Select-String -Path $vigia -Pattern "TIPO 1/4" -SimpleMatch -ErrorAction SilentlyContinue
if ($hit) {
    Write-Host "[OK] vigia_alerts.py contém TIPO 1/4 (código novo)." -ForegroundColor Green
} else {
    Write-Host "[FALHA] vigia_alerts.py NÃO tem TIPO 1/4 — atualização incompleta." -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Checklist .env (NÃO foi alterado automaticamente) ===" -ForegroundColor Yellow
Write-Host @"
Confirme no seu .env (valores yes/no, não true/false no Trust):

  INDICASUS_HOST=10.15.0.222
  INDICASUS_SERVER=10.15.0.222
  INDICASUS_DATABASE=BdSES
  INDICASUS_USER=roneydamaceno
  INDICASUS_PASSWORD=<senha do Roney>
  INDICASUS_ENCRYPT=no
  INDICASUS_TRUST_SERVER_CERTIFICATE=yes
  INDICASUS_USE_DW_CREDENTIALS=false

  ALERT_VIGIA_CATEGORIAS=estado,regional,municipal,cuiaba

  DW_ENCRYPT=no
  DW_TRUST_SERVER_CERTIFICATE=yes

Se aparecer login 'menandes_cievs' no IndicaSUS, a flag USE_DW_CREDENTIALS
ainda está true ou a senha INDICASUS_* está vazia/errada.

Teste sem flood de e-mail:
  ALERT_VIGIA_CATEGORIAS=estado,cuiaba

Comandos:
  .\.venv\Scripts\python.exe preview_alerta_vigia.py
  .\.venv\Scripts\python.exe atualizar_ocupacao_indicasus.py --descobrir
  .\.venv\Scripts\python.exe validar_fontes_dw.py
  .\.venv\Scripts\python.exe run_ciclo_completo.py --force-alert
"@

Write-Host ""
Write-Host "Concluído. Backup em: $BackupDir" -ForegroundColor Green
