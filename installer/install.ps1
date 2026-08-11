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
    [ValidateRange(1, 65535)]
    [int]$ServicePort = 8000,
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
$script:WebhookTokenGenerated = $false
$script:RollbackAvailable = $false
$script:ServiceCreated = $false
$script:ConfigSnapshots = @{}

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

function Invoke-NativeChecked(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$Operation
) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation falhou (codigo de saida $LASTEXITCODE)."
    }
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
        Invoke-NativeChecked 'winget' @(
            'install', '-e', '--id', 'Python.Python.3.11',
            '--accept-package-agreements', '--accept-source-agreements'
        ) 'Instalacao do Python pelo winget'
    } else {
        $url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $out = "$env:TEMP\python-installer.exe"
        Invoke-WebRequest -Uri $url -OutFile $out
        Assert-Authenticode $out 'Python'
        $process = Start-Process -FilePath $out -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1" -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Instalador do Python falhou (codigo $($process.ExitCode))."
        }
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
        Invoke-NativeChecked 'winget' @(
            'install', '-e', '--id', 'OpenJS.NodeJS.LTS',
            '--accept-package-agreements', '--accept-source-agreements'
        ) 'Instalacao do Node.js pelo winget'
    } else {
        $url = "https://nodejs.org/dist/v20.18.0/node-v20.18.0-x64.msi"
        $out = "$env:TEMP\node-installer.msi"
        Invoke-WebRequest -Uri $url -OutFile $out
        Assert-Authenticode $out 'Node.js'
        $process = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$out`" /qn /norestart" -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010)) {
            throw "Instalador do Node.js falhou (codigo $($process.ExitCode))."
        }
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

function Backup-ConfigFiles {
    foreach ($relative in @('backend\.env', 'frontend\.env')) {
        $path = Join-Path $InstallDir $relative
        $exists = Test-Path -LiteralPath $path -PathType Leaf
        $script:ConfigSnapshots[$path] = @{
            Existed = $exists
            Bytes = if ($exists) { [IO.File]::ReadAllBytes($path) } else { $null }
        }
    }
}

function Restore-ConfigFiles {
    foreach ($path in $script:ConfigSnapshots.Keys) {
        $snapshot = $script:ConfigSnapshots[$path]
        if ($snapshot.Existed) {
            $parent = Split-Path $path -Parent
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            [IO.File]::WriteAllBytes($path, [byte[]]$snapshot.Bytes)
        } elseif (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    Write-Warn 'Configuracoes .env restauradas apos falha'
}

function Backup-CurrentCode {
    Backup-ConfigFiles
    $rollback = Join-Path $InstallDir '.rollback-code'
    if (Test-Path $rollback) { Remove-Item -LiteralPath $rollback -Recurse -Force }
    $backend = Join-Path $InstallDir 'backend'
    if (-not (Test-Path (Join-Path $backend 'app'))) { return }

    New-Item -ItemType Directory -Path (Join-Path $rollback 'backend') -Force | Out-Null
    foreach ($dir in @('app', 'alembic', 'scripts')) {
        $source = Join-Path $backend $dir
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $rollback 'backend') -Recurse -Force }
    }
    foreach ($file in @('requirements.txt', 'requirements.lock', 'run.py', 'alembic.ini', '.env.example')) {
        $source = Join-Path $backend $file
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $rollback 'backend') -Force }
    }
    $frontend = Join-Path $InstallDir 'frontend'
    if (Test-Path $frontend) {
        New-Item -ItemType Directory -Path (Join-Path $rollback 'frontend') -Force | Out-Null
        foreach ($dir in @('src', 'public', 'dist')) {
            $source = Join-Path $frontend $dir
            if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $rollback 'frontend') -Recurse -Force }
        }
        foreach ($file in @('package.json', 'package-lock.json', 'vite.config.js', 'index.html', '.env.example')) {
            $source = Join-Path $frontend $file
            if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $rollback 'frontend') -Force }
        }
    }
    $script:RollbackAvailable = $true
    Write-Ok 'Versão anterior preservada para rollback'
}

function Restore-CurrentCode {
    if (-not $script:RollbackAvailable) { return }
    $rollback = Join-Path $InstallDir '.rollback-code'
    foreach ($dir in @('app', 'alembic', 'scripts')) {
        $target = Join-Path $InstallDir "backend\$dir"
        $source = Join-Path $rollback "backend\$dir"
        if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Split-Path $target -Parent) -Recurse -Force }
    }
    foreach ($file in @('requirements.txt', 'requirements.lock', 'run.py', 'alembic.ini', '.env.example')) {
        $source = Join-Path $rollback "backend\$file"
        if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $InstallDir 'backend') -Force }
    }
    foreach ($dir in @('src', 'public', 'dist')) {
        $frontSource = Join-Path $rollback "frontend\$dir"
        $frontTarget = Join-Path $InstallDir "frontend\$dir"
        if (Test-Path $frontTarget) { Remove-Item -LiteralPath $frontTarget -Recurse -Force }
        if (Test-Path $frontSource) {
            Copy-Item -LiteralPath $frontSource -Destination (Split-Path $frontTarget -Parent) -Recurse -Force
        }
    }
    foreach ($file in @('package.json', 'package-lock.json', 'vite.config.js', 'index.html', '.env.example')) {
        $frontSource = Join-Path $rollback "frontend\$file"
        if (Test-Path $frontSource) {
            Copy-Item -LiteralPath $frontSource -Destination (Join-Path $InstallDir 'frontend') -Force
        }
    }
    Write-Warn 'Rollback de código restaurado após falha'
}

function Setup-BackendEnv {
    $backend = Join-Path $InstallDir "backend"
    Push-Location $backend
    try {
        Write-Step "Criando virtualenv Python"
        Invoke-NativeChecked 'python' @('-m', 'venv', '.venv') 'Criacao do virtualenv'
        $pip = Join-Path $backend ".venv\Scripts\pip.exe"
        $py  = Join-Path $backend ".venv\Scripts\python.exe"

        Write-Step "Atualizando pip"
        Invoke-NativeChecked $py @('-m', 'pip', 'install', '--upgrade', 'pip') 'Atualizacao do pip'

        Write-Step "Instalando dependências Python"
        $lock = Join-Path $backend 'requirements.lock'
        if (Test-Path $lock) {
            Invoke-NativeChecked $pip @('install', '--require-hashes', '-r', $lock) 'Instalacao das dependencias Python travadas'
            $lockHash = (Get-FileHash -LiteralPath $lock -Algorithm SHA256).Hash.ToLowerInvariant()
            Set-Content -LiteralPath (Join-Path $backend '.venv\.requirements-lock.sha256') -Value $lockHash -Encoding ASCII
        } else {
            Invoke-NativeChecked $pip @('install', '-r', 'requirements.txt') 'Instalacao das dependencias Python'
        }

        Invoke-NativeChecked $py @('-m', 'pip', 'check') 'Validacao das dependencias Python'

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

function Get-DotEnvValue([string]$path, [string]$key) {
    if (-not (Test-Path $path)) { return $null }
    $pattern = "^\s*$([regex]::Escape($key))\s*=\s*(.*)$"
    foreach ($line in Get-Content $path -Encoding UTF8) {
        if ($line -match $pattern) { return $matches[1].Trim() }
    }
    return $null
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
    $beEnv = Join-Path $InstallDir "backend\.env"
    if (-not $script:BackendEnvCreated) {
        Write-Ok "backend\.env existente preservado (segredos não foram alterados)"
        $webhookToken = Get-DotEnvValue $beEnv 'BREVO_WEBHOOK_TOKEN'
        if ([string]::IsNullOrWhiteSpace($webhookToken) -or $webhookToken.Length -lt 32) {
            Set-DotEnvValue $beEnv 'BREVO_WEBHOOK_TOKEN' (New-RandomHex 32)
            $script:WebhookTokenGenerated = $true
            Write-Warn "BREVO_WEBHOOK_TOKEN ausente/inválido: um novo token foi gravado no .env"
        }
        return
    }

    $script:GeneratedAdminPassword = New-RandomHex 12
    $script:GeneratedDiretorPassword = New-RandomHex 16

    Set-DotEnvValue $beEnv 'BACKEND_ACCESS_KEY' (New-RandomHex 32)
    Set-DotEnvValue $beEnv 'DATA_ENCRYPTION_PASSWORD' (New-RandomHex 32)
    Set-DotEnvValue $beEnv 'SECRET_KEY' (New-RandomHex 32)
    Set-DotEnvValue $beEnv 'BREVO_WEBHOOK_TOKEN' (New-RandomHex 32)
    $script:WebhookTokenGenerated = $true
    Set-DotEnvValue $beEnv 'ADMIN_PASSWORD' $script:GeneratedAdminPassword
    Set-DotEnvValue $beEnv 'DIRETOR_PASSWORD' $script:GeneratedDiretorPassword
    Write-Ok "Chaves e senhas iniciais seguras geradas para a nova instalação"
}

function Configure-BackendEnv {
    $apiHost = if ($ServerIp) { $ServerIp.Trim() } else { Get-LocalLanIPv4 }
    $beEnv   = Join-Path $InstallDir "backend\.env"

    if (Test-Path $beEnv) {
        Set-DotEnvValue $beEnv 'APP_PORT' $ServicePort
        Set-DotEnvValue $beEnv 'CORS_ORIGINS' "http://${apiHost}:$ServicePort"
        if ($apiHost -ne '127.0.0.1' -and $apiHost -ne 'localhost') {
            # O instalador detecta/recebe um endereco de LAN e abre a porta do
            # servico; o Uvicorn precisa escutar fora do loopback tambem.
            Set-DotEnvValue $beEnv 'APP_HOST' '0.0.0.0'
        } else {
            $appHost = Get-DotEnvValue $beEnv 'APP_HOST'
            if ($appHost -in @('127.0.0.1', 'localhost')) {
                Write-Warn "APP_HOST=$appHost aceita somente acesso local."
            }
        }
    }

    if ($apiHost -eq '127.0.0.1') {
        Write-Warn "Não foi possível detectar IP da LAN. Passe -ServerIp 192.168.x.x e rode installer\rebuild-frontend.ps1"
    }
}

function Configure-FrontendEnv {
    if ($SkipFrontend) { return }
    $feEnv = Join-Path $InstallDir "frontend\.env"

    Write-Step "Frontend e API serão servidos na mesma origem"
    Set-DotEnvValue $feEnv 'VITE_API_URL' ''
    Remove-DotEnvKey $feEnv 'VITE_BACKEND_ACCESS_KEY'
}

function Build-Frontend {
    if ($SkipFrontend) { Write-Warn "Frontend ignorado (-SkipFrontend)"; return }
    Configure-FrontendEnv
    $front = Join-Path $InstallDir "frontend"
    Push-Location $front
    try {
        Write-Step "Instalando dependências do frontend"
        Invoke-NativeChecked 'npm' @('ci') 'npm ci'
        Write-Step "Compilando frontend (vite build)"
        Invoke-NativeChecked 'npm' @('run', 'build') 'Build do frontend'
        if (-not (Test-Path (Join-Path $front 'dist\index.html') -PathType Leaf)) {
            throw 'Build do frontend nao gerou dist\index.html.'
        }
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

    # O frontend agora é servido pela API; remove somente o serviço Vite legado.
    if (Get-Service $svcFront -ErrorAction SilentlyContinue) {
        & $nssmExe stop $svcFront 2>$null | Out-Null
        & $nssmExe remove $svcFront confirm 2>$null | Out-Null
    }

    $existingApi = Get-Service $svcApi -ErrorAction SilentlyContinue
    if ($existingApi -and $existingApi.Status -ne 'Stopped') {
        Stop-Service $svcApi -Force -ErrorAction Stop
    }

    Write-Step "Registrando serviço $svcApi"
    if (-not $existingApi) {
        Invoke-NativeChecked $nssmExe @('install', $svcApi, $py, $run) 'Registro do serviço da API'
        $script:ServiceCreated = $true
    }
    Invoke-NativeChecked $nssmExe @('set', $svcApi, 'Application', $py) 'Configuração do executável da API'
    Invoke-NativeChecked $nssmExe @('set', $svcApi, 'AppParameters', $run) 'Configuração dos argumentos da API'
    Invoke-NativeChecked $nssmExe @('set', $svcApi, 'AppDirectory', $backend) 'Configuração do diretório da API'
    Invoke-NativeChecked $nssmExe @('set', $svcApi, 'DisplayName', 'Envio Apolices - API (FastAPI)') 'Configuração do nome do serviço'
    Invoke-NativeChecked $nssmExe @('set', $svcApi, 'Description', 'Backend FastAPI do Sistema de Envio de Apolices') 'Configuração da descrição do serviço'
    Invoke-NativeChecked $nssmExe @('set', $svcApi, 'Start', 'SERVICE_AUTO_START') 'Configuração do início automático'
    New-Item -ItemType Directory -Path (Join-Path $backend "logs") -Force | Out-Null
    Invoke-NativeChecked $nssmExe @('set', $svcApi, 'AppStdout', (Join-Path $backend 'logs\api.out.log')) 'Configuração do log stdout'
    Invoke-NativeChecked $nssmExe @('set', $svcApi, 'AppStderr', (Join-Path $backend 'logs\api.err.log')) 'Configuração do log stderr'

    Write-Step "Iniciando $svcApi"
    Invoke-NativeChecked $nssmExe @('start', $svcApi) 'Inicialização do serviço da API'

    if (-not $SkipFrontend) {
        Write-Ok "Frontend estático será servido pelo próprio backend (mesma origem)"
    }

    Write-Ok "Serviços registrados"
}

function Open-Firewall {
    Write-Step "Liberando porta $ServicePort no firewall"
    $rule = Get-NetFirewallRule -DisplayName 'EnvioApolices-API' -ErrorAction SilentlyContinue
    if ($rule) {
        $rule | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -ErrorAction Stop | Out-Null
        $rule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $ServicePort -ErrorAction Stop | Out-Null
    } else {
        New-NetFirewallRule -DisplayName 'EnvioApolices-API' -Direction Inbound -Protocol TCP -LocalPort $ServicePort -Action Allow -ErrorAction Stop | Out-Null
    }
    Write-Ok "Regra de firewall validada"
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
    Configure-BackendEnv
    Setup-BackendEnv
    Build-Frontend
    Register-Services $nssm
    if (-not $SkipServices) { Assert-DeploymentHealth }
    Open-Firewall
} catch {
    Write-Err "Instalação falhou: $_"
    Restore-CurrentCode
    Restore-ConfigFiles
    if ($script:ServiceCreated) {
        & $nssm stop 'EnvioApolices-API' 2>$null | Out-Null
        & $nssm remove 'EnvioApolices-API' confirm 2>$null | Out-Null
    }
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
if ($script:WebhookTokenGenerated) {
    Write-Host "  Webhook Brevo: um token novo foi salvo em backend\.env." -ForegroundColor Yellow
    Write-Host "  Copie-o para a autenticacao Bearer do webhook no painel Brevo." -ForegroundColor Yellow
}
Write-Host "========================================================" -ForegroundColor Green
