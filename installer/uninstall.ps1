<#
.SYNOPSIS
    Remove serviços e arquivos do Sistema de Envio de Apolices.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\envio-sistema",
    [switch]$KeepData,
    [switch]$RemoveData
)

$ErrorActionPreference = "Continue"

function Write-Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }

$nssmCommand = Get-Command nssm -ErrorAction SilentlyContinue
$nssm = if ($nssmCommand) { $nssmCommand.Source } else { $null }
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

if ($RemoveData) {
    $resolvedInstallDir = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
    $driveRoot = [System.IO.Path]::GetPathRoot($resolvedInstallDir).TrimEnd('\')
    if (-not $resolvedInstallDir -or $resolvedInstallDir -eq $driveRoot) {
        throw "InstallDir inseguro para remoção: $InstallDir"
    }
    Write-Step "Removendo $resolvedInstallDir"
    if (Test-Path -LiteralPath $resolvedInstallDir) {
        Remove-Item -LiteralPath $resolvedInstallDir -Recurse -Force
    }
} else {
    Write-Step "Mantendo $InstallDir por segurança (banco, PDFs, .env e chave de criptografia)"
    Write-Step "Para apagar definitivamente, execute novamente com -RemoveData"
}

Write-Ok "Desinstalação concluída"
