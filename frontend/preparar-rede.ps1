<#
.SYNOPSIS
    Configura o frontend para outros PCs na mesma rede (sem instalar nada nos clientes).

.DESCRIPTION
    - Detecta o IPv4 da LAN deste servidor
    - Atualiza frontend\.env para usar /api na mesma origem, sem embutir segredos
    - Opcional: regra de firewall da API (e do Vite quando -Iniciar) e npm run build
    - Mostra os URLs para partilhar na rede

.EXAMPLE
    .\preparar-rede.ps1
    .\preparar-rede.ps1 -Iniciar
    .\preparar-rede.ps1 -ServerIp 192.168.1.10
#>
[CmdletBinding()]
param(
    [string]$ServerIp = "",
    [string]$HostName = "",
    [switch]$UrlSemPorta,
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontPort = 5173,
    [switch]$SkipBuild,
    [switch]$SkipFirewall,
    [switch]$Iniciar,
    [switch]$SemPausa
)

$ErrorActionPreference = "Stop"
$FrontDir = $PSScriptRoot
$BeEnv    = Join-Path (Split-Path $FrontDir -Parent) "backend\.env"
$FeEnv    = Join-Path $FrontDir ".env"

function Write-Step($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok($m)    { Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Warn($m)  { Write-Host "[!]  $m" -ForegroundColor Yellow }

function Get-LocalLanIPv4 {
    try {
        $all = Get-NetIPConfiguration -ErrorAction Stop |
            Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
            ForEach-Object { $_.IPv4Address.IPAddress } |
            Where-Object { $_ -and $_ -notlike '127.*' -and $_ -notlike '169.254.*' }
        $lan = $all | Where-Object { $_ -like '192.168.*' -or $_ -like '10.*' } | Select-Object -First 1
        if ($lan) { return $lan }
        $other = $all | Where-Object { $_ -notlike '172.31.*' -and $_ -notlike '172.17.*' } | Select-Object -First 1
        if ($other) { return $other }
        if ($all) { return $all | Select-Object -First 1 }
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

function Ensure-NodePath {
    $paths = @(
        $env:NVM_SYMLINK,
        'C:\nvm4w\nodejs',
        "${env:ProgramFiles}\nodejs",
        "${env:LocalAppData}\Programs\node"
    ) | Where-Object { $_ -and (Test-Path (Join-Path $_ 'npm.cmd')) }
    foreach ($p in $paths) {
        if ($env:Path -notlike "*$p*") { $env:Path = "$p;$env:Path" }
    }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw "npm nao encontrado. Instale Node.js LTS ou use preparar-rede.bat a partir de um terminal com Node no PATH."
    }
}

function Invoke-NativeChecked(
    [string]$Command,
    [string[]]$Arguments,
    [string]$Description
) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description falhou (codigo de saida $LASTEXITCODE)."
    }
}

function Open-FirewallPorts {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if (-not $isAdmin) {
        Write-Warn "Firewall: execute como Administrador para abrir as portas necessárias automaticamente."
        return
    }
    $ports = @(@{ Name = 'TF-Envio-API'; Port = $ApiPort })
    if ($Iniciar) {
        $ports += @{ Name = 'TF-Envio-Front-Dev'; Port = $FrontPort }
    }
    foreach ($pair in $ports) {
        $existing = Get-NetFirewallRule -DisplayName $pair.Name -ErrorAction SilentlyContinue
        if ($existing) {
            $existing | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -ErrorAction Stop | Out-Null
            $existing | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $pair.Port -ErrorAction Stop | Out-Null
        } else {
            New-NetFirewallRule -DisplayName $pair.Name -Direction Inbound -Protocol TCP -LocalPort $pair.Port -Action Allow -ErrorAction Stop | Out-Null
        }
        Write-Ok "Firewall: porta $($pair.Port) validada ($($pair.Name))"
    }
}

# --- main ---
Write-Host ""
Write-Host "  Preparar acesso na rede - Terra Fertil" -ForegroundColor White
Write-Host ""

if ($Iniciar -and $ApiPort -ne 8000) {
    throw "-Iniciar usa o proxy do Vite fixo na API :8000. Use -ApiPort 8000 ou inicie apenas o backend na porta personalizada."
}

$hostIp = if ($ServerIp.Trim()) { $ServerIp.Trim() } else { Get-LocalLanIPv4 }
$dnsName = $HostName.Trim().ToLower()
if ($dnsName) {
    $apiUrl = if ($UrlSemPorta) { "http://${dnsName}" } else { "http://${dnsName}:$ApiPort" }
} else {
    $apiUrl = "http://${hostIp}:$ApiPort"
}

Write-Step "IP do servidor na rede: $hostIp"
if ($dnsName) { Write-Step "Nome interno: $dnsName" }
if ($hostIp -eq '127.0.0.1') {
    Write-Warn "Nao foi possivel detectar IP da LAN. Use: .\preparar-rede.ps1 -ServerIp 192.168.x.x"
}

Write-Step "Atualizar $FeEnv"
# Vite em :5173 usa proxy /api -> 127.0.0.1:8000. VITE_API_URL absoluto
# quebra CSP (connect-src 'self') e cookies SameSite=Lax.
Set-DotEnvValue $FeEnv 'VITE_API_URL' ''
# Nunca gravar segredos com prefixo VITE_ (entram no bundle se importados).
Set-DotEnvValue $FeEnv 'VITE_BACKEND_ACCESS_KEY' ''

if (Test-Path $BeEnv) {
    Set-DotEnvValue $BeEnv 'APP_HOST' '0.0.0.0'
    Set-DotEnvValue $BeEnv 'APP_PORT' $ApiPort
    Set-DotEnvValue $BeEnv 'CORS_ORIGINS' $apiUrl
    $enabled = (Get-Content $BeEnv -Encoding UTF8 | Where-Object { $_ -match '^\s*BACKEND_ACCESS_ENABLED\s*=\s*true' })
    if ($enabled) {
        Write-Warn "BACKEND_ACCESS_ENABLED=true: use cookie/header no browser; nao copie a chave para VITE_*."
    }
}
Write-Ok "VITE_API_URL= (vazio - proxy Vite / mesma origem)"
Write-Host "  Sistema:      $apiUrl" -ForegroundColor Gray
if ($Iniciar) { Write-Host "  Vite (dev):   http://${hostIp}:$FrontPort/" -ForegroundColor Gray }

if (-not $SkipFirewall) {
    Write-Step "Firewall"
    Open-FirewallPorts
}

if (-not $SkipBuild) {
    Write-Step "Compilar frontend (npm run build) - necessario para modo producao/preview"
    Ensure-NodePath
    Push-Location $FrontDir
    try {
        if (-not (Test-Path 'node_modules')) {
            if (Test-Path 'package-lock.json') {
                Invoke-NativeChecked -Command 'npm.cmd' -Arguments @('ci') -Description 'Instalacao das dependencias do frontend'
            } else {
                Invoke-NativeChecked -Command 'npm.cmd' -Arguments @('install') -Description 'Instalacao das dependencias do frontend'
            }
        }
        Invoke-NativeChecked -Command 'npm.cmd' -Arguments @('run', 'build') -Description 'Build do frontend'
        if (-not (Test-Path (Join-Path $FrontDir 'dist\index.html'))) {
            throw 'Build do frontend nao gerou dist\index.html.'
        }
        Write-Ok "Build concluido"
    } finally { Pop-Location }
}

if ($dnsName) {
    $urlFront = if ($UrlSemPorta) { "http://${dnsName}" } else { "http://${dnsName}:$ApiPort" }
    $urlApi   = if ($UrlSemPorta) { "http://${dnsName}/api/health" } else { "http://${dnsName}:$ApiPort/api/health" }
} else {
    $urlFront = "http://${hostIp}:$ApiPort"
    $urlApi   = "http://${hostIp}:$ApiPort/api/health"
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Ok  "Pronto. Outros PCs na rede so precisam do browser:"
Write-Host ""
Write-Host "  Sistema (interface):  $urlFront" -ForegroundColor White
Write-Host "  Saude da API:         $urlApi" -ForegroundColor Gray
Write-Host ""
Write-Host "  Neste servidor:" -ForegroundColor Yellow
Write-Host "    Backend a correr (iniciar-backend.bat ou servico :$ApiPort)"
if ($Iniciar) { Write-Host "    Vite de desenvolvimento iniciado separadamente em :$FrontPort" }
Write-Host ""
Write-Host "  Nao use localhost nos outros PCs - use o IP acima." -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""

if ($Iniciar) {
    Write-Step "A iniciar frontend (npm run dev)..."
    Ensure-NodePath
    Push-Location $FrontDir
    try {
        Invoke-NativeChecked -Command 'npm.cmd' -Arguments @('run', 'dev', '--', '--port', [string]$FrontPort) -Description 'Servidor Vite'
    } finally { Pop-Location }
}

if (-not $SemPausa -and -not $Iniciar) {
    Read-Host "Pressione Enter para fechar"
}
