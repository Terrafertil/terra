<#
.SYNOPSIS
    Configura nome interno (ex.: pdf.intranet) para aceder ao sistema na rede.

.DESCRIPTION
    No SERVIDOR (como Administrador):
      - Registo em C:\Windows\System32\drivers\etc\hosts
      - Atualiza frontend\.env, firewall, build (via preparar-rede.ps1)
      - Gera registrar-hostname-nos-pcs.bat para os outros computadores
      - Opcional (-ComProxy): Caddy na porta 80 -> http://pdf.intranet sem :8000

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
    $urlAbrir = if ($semPorta) { "http://$name" } else { "http://${name}:8000" }
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
    if ($existing) {
        $existing | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -ErrorAction Stop | Out-Null
        $existing | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort 80 -ErrorAction Stop | Out-Null
    } else {
        New-NetFirewallRule -DisplayName 'TF-Envio-HTTP' -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -ErrorAction Stop | Out-Null
    }
    Write-Ok "Firewall: porta 80 validada"
}

function Stop-LocalCaddy([string]$caddyExe) {
    $expectedPath = [System.IO.Path]::GetFullPath($caddyExe)
    $processes = Get-Process caddy -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq $expectedPath)
        } catch {
            $false
        }
    }
    foreach ($process in @($processes)) {
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
        Wait-Process -Id $process.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
}

function Install-CaddyIfNeeded {
    $caddyExe = Join-Path $CaddyDir "caddy.exe"
    $ver = "2.11.4"
    if (Test-Path $caddyExe) {
        $versionOutput = & $caddyExe version 2>$null | Select-Object -First 1
        $versionExitCode = $LASTEXITCODE
        if ($versionExitCode -eq 0 -and "$versionOutput" -match "^v$([regex]::Escape($ver))(\s|$)") {
            return $caddyExe
        }
        Write-Step "A atualizar Caddy para v$ver..."
        Stop-LocalCaddy $caddyExe
    }

    Write-Step "A transferir Caddy (proxy HTTP porta 80)..."
    New-Item -ItemType Directory -Path $CaddyDir -Force | Out-Null
    $zipUrl = "https://github.com/caddyserver/caddy/releases/download/v$ver/caddy_${ver}_windows_amd64.zip"
    $zipPath = Join-Path $env:TEMP "caddy_${ver}_windows_amd64.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    # SHA-512 publicado em caddy_2.11.4_checksums.txt no release oficial.
    $expectedSha512 = 'cd5ccfd86a4b40732cf715890d0dca5bf3f63adefec5a7914de85adf240c60ce7e5d2791631b88ef9758e46b23bb1730e020b9c5d696889740b284ffd4788e35'
    $actualSha512 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA512).Hash.ToLowerInvariant()
    if ($actualSha512 -ne $expectedSha512) {
        Remove-Item -LiteralPath $zipPath -Force
        throw "Checksum do Caddy invalido. Download recusado."
    }
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
# O backend :8000 tambem serve o frontend compilado.

http://$name {
    reverse_proxy 127.0.0.1:8000
}
"@ | Set-Content -Path $path -Encoding ASCII
    return $path
}

function Start-CaddyProxy([string]$caddyExe, [string]$caddyfile) {
    Invoke-NativeChecked -Command $caddyExe -Arguments @('validate', '--config', $caddyfile) -Description 'Validacao do Caddyfile'
    Stop-LocalCaddy $caddyExe
    $process = Start-Process -FilePath $caddyExe -ArgumentList @('run', '--config', "`"$caddyfile`"") -WorkingDirectory $CaddyDir -WindowStyle Hidden -PassThru
    try {
        Start-Sleep -Seconds 2
        $process.Refresh()
        if ($process.HasExited) {
            throw "Caddy terminou durante o arranque (codigo de saida $($process.ExitCode))."
        }

        $tcp = New-Object System.Net.Sockets.TcpClient
        try {
            $pending = $tcp.BeginConnect('127.0.0.1', 80, $null, $null)
            if (-not $pending.AsyncWaitHandle.WaitOne(2000)) {
                throw 'Caddy nao abriu a porta 80 dentro do tempo esperado.'
            }
            $tcp.EndConnect($pending)
            if (-not $tcp.Connected) { throw 'Caddy nao esta a aceitar ligacoes na porta 80.' }
        } finally {
            $tcp.Close()
        }
    } catch {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        throw
    }
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
    Write-Host "  (sem :8000 - proxy na porta 80)" -ForegroundColor Gray
} else {
    & (Join-Path $FrontDir "preparar-rede.ps1") @redeArgs
    Write-Host ""
    Write-Host "  Link para partilhar:  http://${name}:8000" -ForegroundColor Green
}

Write-Host ""
Write-Host "  Outros PCs na rede:" -ForegroundColor Yellow
Write-Host "    Opcao A - Copie e execute COMO ADMIN (uma vez em cada PC):" -ForegroundColor Yellow
Write-Host "      $clientBat"
Write-Host "    Opcao B - Pedir a TI: registo DNS tipo A  $name  ->  $ip"
Write-Host ""

if ($Iniciar) {
    Write-Warn "-Iniciar nao abre mais o Vite. Inicie o backend/servico na porta 8000."
}

if (-not $SemPausa -and -not $Iniciar) {
    Read-Host "Pressione Enter para fechar"
}
