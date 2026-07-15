<#
.SYNOPSIS
    Instalador completo do Sistema de Envio de Apolices para Windows Server.

.DESCRIPTION
    - Verifica/instala Python 3.11+ (usa winget se disponível, senão baixa do python.org)
    - Verifica/instala Node.js LTS (para build do frontend)
    - Instala NSSM (gerenciador de serviços Windows) em C:\tools\nssm
    - Cria virtualenv Python e instala requirements do backend
    - Faz npm ci e build reproduzível do frontend
    - Copia .env.example para .env (se não existir)
    - Adiciona as pastas de binários ao PATH do sistema
    - Registra um serviço Windows; a API também serve o frontend estático

.NOTES
    Execute como Administrador no Windows Server.

    Uso:
        Set-ExecutionPolicy -Scope Process Bypass -Force
        .\install.ps1
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "C:\envio-sistema",
    [string]$ServicePort = "8000",
    [string]$FrontPort = "5173", # legado: mantido para compatibilidade, nao e aberto
    # IP ou hostname que os outros PCs usam para chegar à API (ex.: 192.168.1.10).
    # Se vazio, detecta automaticamente o IPv4 da LAN antes do build do frontend.
    [string]$ServerIp = "",
    [switch]$SkipFrontend,
    [switch]$SkipServices
)

$ErrorActionPreference = "Stop"
$script:BackendEnvCreated = $false
$script:GeneratedAdminPassword = $null
$script:GeneratedDiretorPassword = $null
$script:RollbackAvailable = $false

function Write-Step($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "[OK] $msg"    -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "[!]  $msg"    -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "[X]  $msg"    -ForegroundColor Red }

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Err "Este script precisa rodar como Administrador."
        exit 1
    }
}

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Assert-Authenticode([string]$path, [string]$label) {
    $signature = Get-AuthenticodeSignature -FilePath $path
    if ($signature.Status -ne 'Valid') {
        throw "Assinatura digital inválida no instalador de ${label}: $($signature.Status)"
    }
}

function Add-ToSystemPath($path) {
    $current = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($current -notlike "*$path*") {
        Write-Step "Adicionando $path ao PATH do sistema"
        [Environment]::SetEnvironmentVariable("Path", "$current;$path", "Machine")
        # Atualiza a sessão atual também
        $env:Path = "$env:Path;$path"
        Write-Ok "PATH atualizado"
    } else {
        Write-Ok "$path já está no PATH"
    }
}

function Install-Python {
    if (Test-Cmd python) {
        $ver = (python --version) 2>&1
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Python compatível já instalado: $ver"
            return
        }
        Write-Warn "Python incompatível encontrado: $ver. Instalando Python 3.11+."
    }
    Write-Step "Python não encontrado, instalando..."
    if (Test-Cmd winget) {
        winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    } else {
        $url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $out = "$env:TEMP\python-installer.exe"
        Invoke-WebRequest -Uri $url -OutFile $out
        Assert-Authenticode $out 'Python'
        Start-Process -FilePath $out -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1" -Wait
    }
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ não ficou disponível no PATH.' }
    Write-Ok "Python instalado"
}

function Install-Node {
    if (Test-Cmd node) {
        $ver = (node --version) 2>&1
        node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)"
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Node.js compatível já instalado: $ver"
            return
        }
        Write-Warn "Node.js incompatível encontrado: $ver. Instalando Node.js 20+."
    }
    Write-Step "Node.js não encontrado, instalando..."
    if (Test-Cmd winget) {
        winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    } else {
        $url = "https://nodejs.org/dist/v20.18.0/node-v20.18.0-x64.msi"
        $out = "$env:TEMP\node-installer.msi"
        Invoke-WebRequest -Uri $url -OutFile $out
        Assert-Authenticode $out 'Node.js'
        Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$out`" /qn /norestart" -Wait
    }
    node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Node.js 20+ não ficou disponível no PATH.' }
    Write-Ok "Node.js instalado"
}

function Install-NSSM {
    $tools = "C:\tools"
    $nssmDir = Join-Path $tools "nssm"
    $nssmExe = Join-Path $nssmDir "nssm.exe"

    if (Test-Path $nssmExe) {
        Write-Ok "NSSM já instalado em $nssmExe"
        Add-ToSystemPath $nssmDir
        return $nssmExe
    }

    Write-Step "Instalando NSSM em $nssmDir"
    New-Item -ItemType Directory -Path $nssmDir -Force | Out-Null
    $zip = Join-Path $env:TEMP "nssm.zip"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip
    $expectedNssmSha256 = '727D1E42275C605E0F04ABA98095C38A8E1E46DEF453CDFFCE42869428AA6743'
    $actualNssmSha256 = (Get-FileHash -Path $zip -Algorithm SHA256).Hash
    if ($actualNssmSha256 -ne $expectedNssmSha256) {
        Remove-Item -LiteralPath $zip -Force
        throw 'Checksum do NSSM inválido. Download recusado.'
    }
    $tmpExtract = Join-Path $env:TEMP "nssm-extract"
    if (Test-Path $tmpExtract) { Remove-Item -Recurse -Force $tmpExtract }
    Expand-Archive -Path $zip -DestinationPath $tmpExtract -Force

    $src = Get-ChildItem -Path $tmpExtract -Recurse -Filter "nssm.exe" |
           Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
    if (-not $src) {
        $src = Get-ChildItem -Path $tmpExtract -Recurse -Filter "nssm.exe" | Select-Object -First 1
    }
    Copy-Item $src.FullName $nssmExe -Force
    Add-ToSystemPath $nssmDir
    Write-Ok "NSSM instalado"
    return $nssmExe
}

function Deploy-Sources {
    Write-Step "Copiando fontes para $InstallDir"
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

    $root = Split-Path $PSScriptRoot -Parent   # pasta envio-sistema
    $backendSource = Join-Path $root "backend"
    $backendDest = Join-Path $InstallDir "backend"
    New-Item -ItemType Directory -Path $backendDest -Force | Out-Null
    foreach ($dir in @('app', 'alembic', 'scripts')) {
        $target = Join-Path $backendDest $dir
        if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
        Copy-Item -LiteralPath (Join-Path $backendSource $dir) -Destination $backendDest -Recurse -Force
    }
    foreach ($file in @('requirements.txt', 'requirements.lock', 'run.py', 'alembic.ini', '.env.example')) {
        Copy-Item -LiteralPath (Join-Path $backendSource $file) -Destination $backendDest -Force
    }

    if (-not $SkipFrontend) {
        $frontendSource = Join-Path $root "frontend"
        $frontendDest = Join-Path $InstallDir "frontend"
        New-Item -ItemType Directory -Path $frontendDest -Force | Out-Null
        foreach ($dir in @('src', 'public')) {
            $source = Join-Path $frontendSource $dir
            if (Test-Path $source) {
                $target = Join-Path $frontendDest $dir
                if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
                Copy-Item -LiteralPath $source -Destination $frontendDest -Recurse -Force
            }
        }
        foreach ($file in @('package.json', 'package-lock.json', 'vite.config.js', 'index.html', '.env.example')) {
            $source = Join-Path $frontendSource $file
            if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination $frontendDest -Force }
        }
        $oldDist = Join-Path $frontendDest 'dist'
        if (Test-Path $oldDist) { Remove-Item -LiteralPath $oldDist -Recurse -Force }
    }
    $installerDest = Join-Path $InstallDir "installer"
    New-Item -ItemType Directory -Path $installerDest -Force | Out-Null
    foreach ($file in @('install.ps1', 'uninstall.ps1', 'rebuild-frontend.ps1', 'README-INSTALL.md')) {
        $source = Join-Path $PSScriptRoot $file
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination $installerDest -Force }
    }

    Write-Ok "Código copiado sem .env, banco, PDFs, backups, logs, .venv ou node_modules"

    # .env
    $envExample = Join-Path $InstallDir "backend\.env.example"
    $envFile    = Join-Path $InstallDir "backend\.env"
    if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
        Copy-Item $envExample $envFile
        $script:BackendEnvCreated = $true
        Write-Ok "Criado backend\.env (configure as credenciais SMTP da Brevo antes de enviar)"
    }

    if (-not $SkipFrontend) {
        $feEnvEx = Join-Path $InstallDir "frontend\.env.example"
        $feEnv   = Join-Path $InstallDir "frontend\.env"
        if (-not (Test-Path $feEnv) -and (Test-Path $feEnvEx)) {
            Copy-Item $feEnvEx $feEnv
        }
    }
}

function Backup-CurrentCode {
    $rollback = Join-Path $InstallDir '.rollback-code'
    if (Test-Path $rollback) { Remove-Item -LiteralPath $rollback -Recurse -Force }
    $backend = Join-Path $InstallDir 'backend'
    if (-not (Test-Path (Join-Path $backend 'app'))) { return }

    New-Item -ItemType Directory -Path (Join-Path $rollback 'backend') -Force | Out-Null
    foreach ($dir in @('app', 'alembic')) {
        $source = Join-Path $backend $dir
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $rollback 'backend') -Recurse -Force }
    }
    foreach ($file in @('requirements.txt', 'requirements.lock', 'run.py', 'alembic.ini')) {
        $source = Join-Path $backend $file
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $rollback 'backend') -Force }
    }
    $frontDist = Join-Path $InstallDir 'frontend\dist'
    if (Test-Path $frontDist) {
        New-Item -ItemType Directory -Path (Join-Path $rollback 'frontend') -Force | Out-Null
        Copy-Item -LiteralPath $frontDist -Destination (Join-Path $rollback 'frontend') -Recurse -Force
    }
    $script:RollbackAvailable = $true
    Write-Ok 'Versão anterior preservada para rollback'
}

function Restore-CurrentCode {
    if (-not $script:RollbackAvailable) { return }
    $rollback = Join-Path $InstallDir '.rollback-code'
    foreach ($dir in @('app', 'alembic')) {
        $target = Join-Path $InstallDir "backend\$dir"
        $source = Join-Path $rollback "backend\$dir"
        if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Split-Path $target -Parent) -Recurse -Force }
    }
    foreach ($file in @('requirements.txt', 'requirements.lock', 'run.py', 'alembic.ini')) {
        $source = Join-Path $rollback "backend\$file"
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $InstallDir 'backend') -Force }
    }
    $frontSource = Join-Path $rollback 'frontend\dist'
    $frontTarget = Join-Path $InstallDir 'frontend\dist'
    if (Test-Path $frontTarget) { Remove-Item -LiteralPath $frontTarget -Recurse -Force }
    if (Test-Path $frontSource) {
        Copy-Item -LiteralPath $frontSource -Destination (Split-Path $frontTarget -Parent) -Recurse -Force
    }
    Write-Warn 'Rollback de código restaurado após falha'
}

function Setup-BackendEnv {
    $backend = Join-Path $InstallDir "backend"
    Push-Location $backend
    try {
        Write-Step "Criando virtualenv Python"
        python -m venv .venv
        $pip = Join-Path $backend ".venv\Scripts\pip.exe"
        $py  = Join-Path $backend ".venv\Scripts\python.exe"

        Write-Step "Atualizando pip"
        & $py -m pip install --upgrade pip

        Write-Step "Instalando dependências Python"
        $lock = Join-Path $backend 'requirements.lock'
        if (Test-Path $lock) {
            & $pip install --require-hashes -r $lock
        } else {
            & $pip install -r requirements.txt
        }

        Write-Ok "Backend preparado"
    } finally { Pop-Location }
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

    $fallback = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        Select-Object -ExpandProperty IPAddress -First 1
    if ($fallback) { return $fallback }
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

function New-RandomHex([int]$bytes = 32) {
    $buffer = New-Object byte[] $bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    } finally {
        $rng.Dispose()
    }
    return -join ($buffer | ForEach-Object { $_.ToString('x2') })
}

function Initialize-FreshBackendEnv {
    if (-not $script:BackendEnvCreated) {
        Write-Ok "backend\.env existente preservado (segredos não foram alterados)"
        return
    }

    $beEnv = Join-Path $InstallDir "backend\.env"
    $script:GeneratedAdminPassword = New-RandomHex 12
    $script:GeneratedDiretorPassword = New-RandomHex 16

    Set-DotEnvValue $beEnv 'BACKEND_ACCESS_KEY' (New-RandomHex 32)
    Set-DotEnvValue $beEnv 'DATA_ENCRYPTION_PASSWORD' (New-RandomHex 32)
    Set-DotEnvValue $beEnv 'SECRET_KEY' (New-RandomHex 32)
    Set-DotEnvValue $beEnv 'BREVO_WEBHOOK_TOKEN' (New-RandomHex 32)
    Set-DotEnvValue $beEnv 'ADMIN_PASSWORD' $script:GeneratedAdminPassword
    Set-DotEnvValue $beEnv 'DIRETOR_PASSWORD' $script:GeneratedDiretorPassword
    Write-Ok "Chaves e senhas iniciais seguras geradas para a nova instalação"
}

function Configure-FrontendEnv {
    if ($SkipFrontend) { return }

    $apiHost = if ($ServerIp) { $ServerIp.Trim() } else { Get-LocalLanIPv4 }
    $feEnv   = Join-Path $InstallDir "frontend\.env"
    $beEnv   = Join-Path $InstallDir "backend\.env"

    Write-Step "Frontend e API serão servidos na mesma origem"
    Set-DotEnvValue $feEnv 'VITE_API_URL' ''
    Remove-DotEnvKey $feEnv 'VITE_BACKEND_ACCESS_KEY'

    if (Test-Path $beEnv) {
        Set-DotEnvValue $beEnv 'CORS_ORIGINS' "http://${apiHost}:$ServicePort"
    }

    if ($apiHost -eq '127.0.0.1') {
        Write-Warn "Não foi possível detectar IP da LAN. Passe -ServerIp 192.168.x.x e rode installer\rebuild-frontend.ps1"
    }
}

function Build-Frontend {
    if ($SkipFrontend) { Write-Warn "Frontend ignorado (-SkipFrontend)"; return }
    Configure-FrontendEnv
    $front = Join-Path $InstallDir "frontend"
    Push-Location $front
    try {
        Write-Step "Instalando dependências do frontend"
        & npm ci
        Write-Step "Compilando frontend (vite build)"
        & npm run build
        Write-Ok "Frontend compilado em frontend\dist"
    } finally { Pop-Location }
}

function Register-Services([string]$nssmExe) {
    if ($SkipServices) { Write-Warn "Registro de serviços ignorado (-SkipServices)"; return }

    $svcApi   = "EnvioApolices-API"
    $svcFront = "EnvioApolices-Front"
    $backend  = Join-Path $InstallDir "backend"
    $py       = Join-Path $backend ".venv\Scripts\python.exe"
    $run      = Join-Path $backend "run.py"

    # Remove serviços antigos (se existirem)
    foreach ($s in @($svcApi, $svcFront)) {
        & $nssmExe stop $s 2>$null | Out-Null
        & $nssmExe remove $s confirm 2>$null | Out-Null
    }

    Write-Step "Registrando serviço $svcApi"
    & $nssmExe install $svcApi $py $run
    & $nssmExe set $svcApi AppDirectory $backend
    & $nssmExe set $svcApi DisplayName "Envio Apolices - API (FastAPI)"
    & $nssmExe set $svcApi Description "Backend FastAPI do Sistema de Envio de Apolices"
    & $nssmExe set $svcApi Start SERVICE_AUTO_START
    & $nssmExe set $svcApi AppStdout (Join-Path $backend "logs\api.out.log")
    & $nssmExe set $svcApi AppStderr (Join-Path $backend "logs\api.err.log")
    New-Item -ItemType Directory -Path (Join-Path $backend "logs") -Force | Out-Null

    Write-Step "Iniciando $svcApi"
    & $nssmExe start $svcApi

    if (-not $SkipFrontend) {
        Write-Ok "Frontend estático será servido pelo próprio backend (mesma origem)"
    }

    Write-Ok "Serviços registrados"
}

function Open-Firewall {
    Write-Step "Liberando porta $ServicePort no firewall"
    try {
        New-NetFirewallRule -DisplayName "EnvioApolices-API"   -Direction Inbound -Protocol TCP -LocalPort $ServicePort -Action Allow -ErrorAction SilentlyContinue | Out-Null
        Write-Ok "Regras de firewall criadas"
    } catch {
        Write-Warn "Falha ao criar regras de firewall: $_"
    }
}

function Assert-DeploymentHealth {
    Write-Step 'Validando saúde da API e do painel'
    $lastError = $null
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ServicePort/api/health" -TimeoutSec 2
            $front = Invoke-WebRequest -Uri "http://127.0.0.1:$ServicePort/" -UseBasicParsing -TimeoutSec 2
            if ($health.status -eq 'ok' -and ($SkipFrontend -or $front.Content -match '<div id="app">')) {
                Write-Ok 'Health check concluído'
                return
            }
        } catch { $lastError = $_ }
        Start-Sleep -Seconds 1
    }
    throw "Health check falhou: $lastError"
}

# ============== MAIN ==============
Assert-Admin
Write-Step "Instalando em $InstallDir"

Install-Python
if (-not $SkipFrontend) { Install-Node }
$nssm = Install-NSSM

Backup-CurrentCode
try {
    Deploy-Sources
    Initialize-FreshBackendEnv
    Setup-BackendEnv
    Build-Frontend
    Open-Firewall
    Register-Services $nssm
    if (-not $SkipServices) { Assert-DeploymentHealth }
} catch {
    Write-Err "Instalação falhou: $_"
    Restore-CurrentCode
    $service = Get-Service 'EnvioApolices-API' -ErrorAction SilentlyContinue
    if ($service) { Restart-Service 'EnvioApolices-API' -Force -ErrorAction SilentlyContinue }
    throw
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Ok  "Instalação concluída."
$shownIp = if ($ServerIp) { $ServerIp.Trim() } else { Get-LocalLanIPv4 }
Write-Host "  Saude da API: http://${shownIp}:$ServicePort/api/health" -ForegroundColor White
Write-Host "  Frontend:     http://${shownIp}:$ServicePort"       -ForegroundColor White
Write-Host "  (Nos outros PCs use o IP acima - nunca localhost)" -ForegroundColor Yellow
Write-Host "  Serviços:     Get-Service EnvioApolices-*"               -ForegroundColor White
Write-Host "  Config:       $InstallDir\backend\.env"                  -ForegroundColor White
if ($script:BackendEnvCreated) {
    Write-Host "  Login admin:  admin / $script:GeneratedAdminPassword"     -ForegroundColor Yellow
    Write-Host "  Login diretor: admindiretor / $script:GeneratedDiretorPassword" -ForegroundColor Yellow
    Write-Host "  Guarde essas senhas e troque-as no primeiro login."       -ForegroundColor Yellow
}
Write-Host "========================================================" -ForegroundColor Green
