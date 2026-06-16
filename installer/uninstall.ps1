<#
.SYNOPSIS
    Remove serviços e arquivos do Sistema de Envio de Apolices.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\envio-sistema",
    [switch]$KeepData
)

$ErrorActionPreference = "Continue"

function Write-Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }

$nssm = (Get-Command nssm -ErrorAction SilentlyContinue)?.Source
if (-not $nssm) { $nssm = "C:\tools\nssm\nssm.exe" }

foreach ($svc in @("EnvioApolices-API", "EnvioApolices-Front")) {
    if (Test-Path $nssm) {
        Write-Step "Parando/removendo serviço $svc"
        & $nssm stop $svc 2>$null | Out-Null
        & $nssm remove $svc confirm 2>$null | Out-Null
    }
}

Write-Step "Removendo regras de firewall"
Remove-NetFirewallRule -DisplayName "EnvioApolices-API"   -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName "EnvioApolices-Front" -ErrorAction SilentlyContinue

if (-not $KeepData) {
    Write-Step "Removendo $InstallDir"
    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
    }
} else {
    Write-Step "Mantendo pasta $InstallDir (parâmetro -KeepData)"
}

Write-Ok "Desinstalação concluída"
