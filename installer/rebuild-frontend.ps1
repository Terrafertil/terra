<#
.SYNOPSIS
    Recompila o frontend para ser servido pelo backend na mesma origem.

.EXAMPLE
    .\rebuild-frontend.ps1 -ServerIp 192.168.1.50
    .\rebuild-frontend.ps1 -InstallDir C:\envio-sistema
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\envio-sistema",
    [string]$ServicePort = "8000",
    [string]$ServerIp = ""
)

$ErrorActionPreference = "Stop"
$front = Join-Path $InstallDir "frontend"
if (-not (Test-Path (Join-Path $front "package.json"))) {
    Write-Host "[X] Pasta frontend não encontrada em $InstallDir" -ForegroundColor Red
    exit 1
}

function Get-LocalLanIPv4 {
    try {
        $ip = Get-NetIPConfiguration -ErrorAction Stop |
            Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
            ForEach-Object { $_.IPv4Address.IPAddress } |
            Where-Object { $_ -and $_ -notlike '127.*' -and $_ -notlike '169.254.*' } |
            Select-Object -First 1
        if ($ip) { return $ip }
    } catch { }
    return '127.0.0.1'
}

function Set-DotEnvValue([string]$path, [string]$key, [string]$value) {
    $lines = if (Test-Path $path) { Get-Content $path -Encoding UTF8 } else { @() }
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($key))\s*=") {
            $found = $true
            "$key=$value"
        } else { $line }
    }
    if (-not $found) { $out += "$key=$value" }
    $out | Set-Content -Path $path -Encoding UTF8
}

function Remove-DotEnvKey([string]$path, [string]$key) {
    if (-not (Test-Path $path)) { return }
    $pattern = "^\s*$([regex]::Escape($key))\s*="
    @(Get-Content $path -Encoding UTF8 | Where-Object { $_ -notmatch $pattern }) |
        Set-Content -Path $path -Encoding UTF8
}

$apiHost = if ($ServerIp) { $ServerIp.Trim() } else { Get-LocalLanIPv4 }
$feEnv   = Join-Path $front ".env"
$beEnv   = Join-Path $InstallDir "backend\.env"

Write-Host "==> Frontend e API na mesma origem" -ForegroundColor Cyan
Set-DotEnvValue $feEnv 'VITE_API_URL' ''
Remove-DotEnvKey $feEnv 'VITE_BACKEND_ACCESS_KEY'

Push-Location $front
try {
    npm run build
} finally { Pop-Location }

$svc = Get-Service -Name 'EnvioApolices-API' -ErrorAction SilentlyContinue
if ($svc) {
    Restart-Service EnvioApolices-API
    Write-Host "[OK] Serviço EnvioApolices-API reiniciado" -ForegroundColor Green
} else {
    Write-Host "[!] Serviço não encontrado. Reinicie manualmente a API." -ForegroundColor Yellow
}

Write-Host "[OK] Nos outros PCs abra: http://${apiHost}:$ServicePort" -ForegroundColor Green
