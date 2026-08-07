#Requires -Version 5.1
<#
.SYNOPSIS
  Cria tarefas do Agendador Windows para o SIS Clima-Saúde (CIEVS/SES-MT).

Rotina (docs/OPERACAO.md):
  07:30 — regeneração completa (pipeline + enrichment)
  12:00 — reprocessamento (--skip-pipeline se quiser mais rápido; aqui full para críticos)
  17:00 — reprocessamento + digest de alertas (sem --force)

Uso (PowerShell como usuário atual):
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\criar_tarefas_windows.ps1
#>
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PipelineBat = Join-Path $Root "rodar_pipeline.bat"
$AlertasBat = Join-Path $Root "rodar_alertas_once.bat"

if (-not (Test-Path $PipelineBat)) { throw "Não encontrado: $PipelineBat" }
if (-not (Test-Path $AlertasBat)) { throw "Não encontrado: $AlertasBat" }

function Register-SisTask {
    param(
        [string]$Name,
        [string]$Bat,
        [string]$Args,
        [string]$Time,   # HH:mm
        [string]$Description
    )
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Bat`" $Args" -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 4)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $Description | Out-Null
    Write-Host "OK  $Name @ $Time"
}

Register-SisTask `
    -Name "SIS_Clima_Pipeline_0730" `
    -Bat $PipelineBat `
    -Args "" `
    -Time "07:30" `
    -Description "SIS Clima-Saúde: regeneração completa diária 07h30 (CIEVS/SES-MT)"

Register-SisTask `
    -Name "SIS_Clima_Reprocess_1200" `
    -Bat $PipelineBat `
    -Args "" `
    -Time "12:00" `
    -Description "SIS Clima-Saúde: reprocessamento 12h (níveis críticos)"

Register-SisTask `
    -Name "SIS_Clima_Reprocess_1700" `
    -Bat $PipelineBat `
    -Args "" `
    -Time "17:00" `
    -Description "SIS Clima-Saúde: reprocessamento 17h (níveis críticos)"

Register-SisTask `
    -Name "SIS_Clima_Alertas_0815" `
    -Bat $AlertasBat `
    -Args "" `
    -Time "08:15" `
    -Description "SIS Clima-Saúde: digest SES/CIEVS 08h15 (sem force; Docker loop também ativo)"

Write-Host ""
Write-Host "Tarefas registradas. Listagem:"
Get-ScheduledTask -TaskName "SIS_Clima_*" | Select-Object TaskName, State | Format-Table -AutoSize
Write-Host "Nota: o container Docker sis_clima_alerts (--loop) continua como canal principal de digest."
Write-Host "Envio real depende de SEND_ALERT_ON_LEVEL_CHANGE e canais no .env."
