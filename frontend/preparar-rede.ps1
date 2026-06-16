<#
.SYNOPSIS
    Configura o frontend para outros PCs na mesma rede (sem instalar nada nos clientes).

.DESCRIPTION
    - Detecta o IPv4 da LAN deste servidor
    - Atualiza frontend\.env (VITE_API_URL + chave do backend, se existir)
    - Opcional: regras de firewall (8000 e 5173) e npm run build
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
    [int]$ApiPort = 8000,
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
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm nao encontrado. Instale Node.js LTS ou use preparar-rede.bat a partir de um terminal com Node no PATH."
    }
}

function Open-FirewallPorts {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if (-not $isAdmin) {
        Write-Warn "Firewall: execute como Administrador para abrir as portas $ApiPort e $FrontPort automaticamente."
        return
    }
    foreach ($pair in @(
        @{ Name = 'TF-Envio-API'; Port = $ApiPort },
        @{ Name = 'TF-Envio-Front'; Port = $FrontPort }
    )) {
        $existing = Get-NetFirewallRule -DisplayName $pair.Name -ErrorAction SilentlyContinue
        if (-not $existing) {
            New-NetFirewallRule -DisplayName $pair.Name -Direction Inbound -Protocol TCP -LocalPort $pair.Port -Action Allow | Out-Null
            Write-Ok "Firewall: porta $($pair.Port) ($($pair.Name))"
        } else {
            Write-Ok "Firewall: regra $($pair.Name) ja existe"
        }
    }
}

# --- main ---
Write-Host ""
Write-Host "  Preparar acesso na rede - Terra Fertil" -ForegroundColor White
Write-Host ""

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
Set-DotEnvValue $FeEnv 'VITE_API_URL' $apiUrl

if (Test-Path $BeEnv) {
    $enabled = (Get-Content $BeEnv -Encoding UTF8 | Where-Object { $_ -match '^\s*BACKEND_ACCESS_ENABLED\s*=\s*true' })
    $bkLine  = Get-Content $BeEnv -Encoding UTF8 | Where-Object { $_ -match '^\s*BACKEND_ACCESS_KEY\s*=' } | Select-Object -First 1
    if ($bkLine -match '=\s*(.+)$') {
        $bkVal = $Matches[1].Trim().Trim('"').Trim("'")
        if ($bkVal -and $bkVal -notmatch 'cole-a') {
            Set-DotEnvValue $FeEnv 'VITE_BACKEND_ACCESS_KEY' $bkVal
            Write-Ok "Chave VITE_BACKEND_ACCESS_KEY alinhada com backend\.env"
        } elseif ($enabled) {
            Write-Warn "BACKEND_ACCESS_ENABLED=true mas BACKEND_ACCESS_KEY vazia no backend\.env"
        } else {
            Set-DotEnvValue $FeEnv 'VITE_BACKEND_ACCESS_KEY' ''
        }
    }
}
Write-Ok "VITE_API_URL=$apiUrl"

if (-not $SkipFirewall) {
    Write-Step "Firewall (portas $ApiPort e $FrontPort)"
    try { Open-FirewallPorts } catch { Write-Warn "Firewall: $_" }
}

if (-not $SkipBuild) {
    Write-Step "Compilar frontend (npm run build) - necessario para modo producao/preview"
    Ensure-NodePath
    Push-Location $FrontDir
    try {
        if (-not (Test-Path 'node_modules')) {
            npm install
        }
        npm run build
        Write-Ok "Build concluido"
    } finally { Pop-Location }
}

if ($dnsName) {
    $urlFront = if ($UrlSemPorta) { "http://${dnsName}" } else { "http://${dnsName}:$FrontPort" }
    $urlApi   = if ($UrlSemPorta) { "http://${dnsName}/docs" } else { "http://${dnsName}:$ApiPort/docs" }
} else {
    $urlFront = "http://${hostIp}:$FrontPort"
    $urlApi   = "http://${hostIp}:$ApiPort/docs"
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Ok  "Pronto. Outros PCs na rede so precisam do browser:"
Write-Host ""
Write-Host "  Sistema (interface):  $urlFront" -ForegroundColor White
Write-Host "  API (teste):          $urlApi" -ForegroundColor Gray
Write-Host ""
Write-Host "  Neste servidor:" -ForegroundColor Yellow
Write-Host "    1. Backend a correr (iniciar-backend.bat ou servico :$ApiPort)"
Write-Host "    2. Frontend: iniciar-frontend.bat  OU  npm run preview"
Write-Host ""
Write-Host "  Nao use localhost nos outros PCs - use o IP acima." -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""

if ($Iniciar) {
    Write-Step "A iniciar frontend (npm run dev)..."
    Ensure-NodePath
    Push-Location $FrontDir
    try { npm run dev } finally { Pop-Location }
}

if (-not $SemPausa -and -not $Iniciar) {
    Read-Host "Pressione Enter para fechar"
}
