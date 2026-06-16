<#
.SYNOPSIS
    Configura nome interno (ex.: pdf.intranet) para aceder ao sistema na rede.

.DESCRIPTION
    No SERVIDOR (como Administrador):
      - Registo em C:\Windows\System32\drivers\etc\hosts
      - Atualiza frontend\.env, firewall, build (via preparar-rede.ps1)
      - Gera registrar-hostname-nos-pcs.bat para os outros computadores
      - Opcional (-ComProxy): Caddy na porta 80 -> http://pdf.intranet sem :5173

    Nos outros PCs: executar UMA VEZ o .bat gerado (como Admin) OU pedir registo DNS a TI.

.EXAMPLE
    .\preparar-intranet.ps1
    .\preparar-intranet.ps1 -HostName apolices.terrafertil.local
    .\preparar-intranet.ps1 -ComProxy
#>
[CmdletBinding()]
param(
    [string]$HostName = "pdf.intranet",
    [string]$ServerIp = "",
    [switch]$ComProxy,
    [switch]$SkipBuild,
    [switch]$Iniciar,
    [switch]$SemPausa
)

$ErrorActionPreference = "Stop"
$FrontDir = $PSScriptRoot
$RootDir  = Split-Path $FrontDir -Parent
$CaddyDir = Join-Path $RootDir "tools\caddy"
$Marker   = "# terra-fertil-envio-apolices"

function Write-Step($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok($m)    { Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Warn($m)  { Write-Host "[!]  $m" -ForegroundColor Yellow }

function Test-IsAdmin {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

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

function Set-HostsRecord([string]$ip, [string]$name) {
    $hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
    $lines = Get-Content $hostsPath -Encoding UTF8
    $filtered = $lines | Where-Object {
        $_ -notmatch [regex]::Escape($Marker) -and
        $_ -notmatch "(\s|^)$([regex]::Escape($name))(\s|$)"
    }
    $filtered += "$Marker"
    $filtered += "$ip`t$name"
    $filtered | Set-Content -Path $hostsPath -Encoding UTF8
    Write-Ok "hosts: $name -> $ip (neste servidor)"
}

function New-ClienteHostsScript([string]$ip, [string]$name, [string]$outPath, [bool]$semPorta) {
    $urlAbrir = if ($semPorta) { "http://$name" } else { "http://${name}:5173" }
    $bat = @"
@echo off
title Registrar $name nos PCs da rede
REM Execute como Administrador em cada PC (uma vez).
REM Ou peca a TI: registo DNS A  $name  ->  $ip

net session >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Clique com o botao direito e "Executar como administrador".
  pause
  exit /b 1
)

set HOSTS=%SystemRoot%\System32\drivers\etc\hosts
findstr /I /C:"$name" "%HOSTS%" >nul 2>&1
if not errorlevel 1 (
  echo [OK] $name ja existe em hosts neste PC.
  goto :done
)

echo $Marker>> "%HOSTS%"
echo $ip    $name>> "%HOSTS%"
echo [OK] Adicionado: $ip  $name

:done
echo.
echo Abra no browser: $urlAbrir
pause
"@
    $bat | Set-Content -Path $outPath -Encoding ASCII
    Write-Ok "Script para outros PCs: $outPath"
}

function Open-FirewallPort80 {
    $existing = Get-NetFirewallRule -DisplayName 'TF-Envio-HTTP' -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-NetFirewallRule -DisplayName 'TF-Envio-HTTP' -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow | Out-Null
        Write-Ok "Firewall: porta 80 aberta"
    }
}

function Install-CaddyIfNeeded {
    $caddyExe = Join-Path $CaddyDir "caddy.exe"
    if (Test-Path $caddyExe) { return $caddyExe }

    Write-Step "A transferir Caddy (proxy HTTP porta 80)..."
    New-Item -ItemType Directory -Path $CaddyDir -Force | Out-Null
    $ver = "2.8.4"
    $zipUrl = "https://github.com/caddyserver/caddy/releases/download/v$ver/caddy_${ver}_windows_amd64.zip"
    $zipPath = Join-Path $env:TEMP "caddy.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    Expand-Archive -Path $zipPath -DestinationPath $CaddyDir -Force
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path $caddyExe)) { throw "caddy.exe nao encontrado apos extracao em $CaddyDir" }
    Write-Ok "Caddy instalado em $CaddyDir"
    return $caddyExe
}

function Write-Caddyfile([string]$name) {
    $path = Join-Path $CaddyDir "Caddyfile"
    @"
# Gerado por preparar-intranet.ps1 - Terra Fertil
# Requer backend :8000 e frontend :5173 a correr neste servidor.

http://$name {
    handle /api* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /docs* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /openapi.json {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        reverse_proxy 127.0.0.1:5173
    }
}
"@ | Set-Content -Path $path -Encoding UTF8
    return $path
}

function Start-CaddyProxy([string]$caddyExe, [string]$caddyfile) {
    Get-Process caddy -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*\tools\caddy\*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath $caddyExe -ArgumentList "run", "--config", $caddyfile -WorkingDirectory $CaddyDir -WindowStyle Hidden
    Start-Sleep -Seconds 2
    Write-Ok "Caddy a correr (proxy http://$($HostName.Trim().ToLower()) na porta 80)"
    Write-Warn "Para parar: feche o processo caddy.exe ou reinicie o servidor."
}

# --- main ---
Write-Host ""
Write-Host "  Preparar nome interno (intranet) - Terra Fertil" -ForegroundColor White
Write-Host ""

if (-not (Test-IsAdmin)) {
    Write-Warn "Execute como Administrador (hosts + firewall + proxy)."
    Write-Host "       Clique direito em preparar-intranet.bat -> Executar como administrador"
    if (-not $SemPausa) { Read-Host "Enter para sair"; exit 1 }
    exit 1
}

$name = $HostName.Trim().ToLower()
if (-not $name -or $name -notmatch '^[a-z0-9]([a-z0-9\-\.]*[a-z0-9])?$') {
    throw "HostName invalido: use apenas letras, numeros, pontos e hifens (ex.: pdf.intranet)"
}

$ip = if ($ServerIp.Trim()) { $ServerIp.Trim() } else { Get-LocalLanIPv4 }
if ($ip -eq '127.0.0.1') {
    Write-Warn "IP da LAN nao detectado. Use -ServerIp 192.168.x.x"
}

Write-Step "Nome: $name  |  IP do servidor: $ip"
Set-HostsRecord $ip $name

$clientBat = Join-Path $FrontDir "registrar-hostname-nos-pcs.bat"
New-ClienteHostsScript $ip $name $clientBat ([bool]$ComProxy)

$redeArgs = @{
    ServerIp     = $ip
    HostName     = $name
    UrlSemPorta  = [bool]$ComProxy
    SkipFirewall = $false
    SemPausa     = $true
}
if ($SkipBuild) { $redeArgs['SkipBuild'] = $true }

if ($ComProxy) {
    Write-Step "Proxy HTTP (porta 80) com Caddy"
    Open-FirewallPort80
    $caddyExe = Install-CaddyIfNeeded
    $caddyfile = Write-Caddyfile $name
    Start-CaddyProxy $caddyExe $caddyfile
    $redeArgs['SkipFirewall'] = $true
    & (Join-Path $FrontDir "preparar-rede.ps1") @redeArgs
    Write-Host ""
    Write-Host "  Link para partilhar:  http://$name" -ForegroundColor Green
    Write-Host "  (sem :5173 - proxy na porta 80)" -ForegroundColor Gray
} else {
    & (Join-Path $FrontDir "preparar-rede.ps1") @redeArgs
    Write-Host ""
    Write-Host "  Link para partilhar:  http://${name}:5173" -ForegroundColor Green
}

Write-Host ""
Write-Host "  Outros PCs na rede:" -ForegroundColor Yellow
Write-Host "    Opcao A - Copie e execute COMO ADMIN (uma vez em cada PC):" -ForegroundColor Yellow
Write-Host "      $clientBat"
Write-Host "    Opcao B - Pedir a TI: registo DNS tipo A  $name  ->  $ip"
Write-Host ""

if ($Iniciar) {
    & (Join-Path $FrontDir "preparar-rede.ps1") -Iniciar -SemPausa -SkipBuild -SkipFirewall -HostName $name -ServerIp $ip -UrlSemPorta:$ComProxy
}

if (-not $SemPausa -and -not $Iniciar) {
    Read-Host "Pressione Enter para fechar"
}
