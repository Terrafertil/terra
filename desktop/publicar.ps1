[CmdletBinding()]
param(
    [string]$Runtime = "win-x64",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$OutputDir = if ($OutputDir) { $OutputDir } else { Join-Path $PSScriptRoot "publish" }
$project = Join-Path $PSScriptRoot "TerraFertil.Desktop\TerraFertil.Desktop.csproj"

$localDotnet = Join-Path (Split-Path $PSScriptRoot -Parent) ".dotnet-sdk\dotnet.exe"
$dotnet = if (Get-Command dotnet -ErrorAction SilentlyContinue) {
    "dotnet"
} elseif (Test-Path $localDotnet) {
    $localDotnet
} else {
    $null
}

if (-not $dotnet) {
    throw "SDK do .NET 8 não encontrado. Instale-o em https://dotnet.microsoft.com/download/dotnet/8.0"
}

& $dotnet restore $project
if ($LASTEXITCODE -ne 0) { throw "Falha ao restaurar dependências." }
& $dotnet publish $project --configuration Release --runtime $Runtime --self-contained true `
    --output $OutputDir -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
    -p:DebugType=None -p:DebugSymbols=false
if ($LASTEXITCODE -ne 0) { throw "Falha ao publicar o aplicativo." }

Write-Host "Aplicativo publicado em: $OutputDir" -ForegroundColor Green
Write-Host "Execute: $(Join-Path $OutputDir 'TerraFertil.exe')" -ForegroundColor Green
