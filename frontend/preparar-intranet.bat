@echo off
setlocal
cd /d "%~dp0"
title Preparar pdf.intranet - Terra Fertil

net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo [AVISO] Execute como Administrador para configurar hosts e firewall.
  echo         Clique direito neste ficheiro -^> "Executar como administrador"
  echo.
  pause
  exit /b 1
)

if defined NVM_SYMLINK if exist "%NVM_SYMLINK%\npm.cmd" set "PATH=%NVM_SYMLINK%;%PATH%"
if exist "C:\nvm4w\nodejs\npm.cmd" set "PATH=C:\nvm4w\nodejs;%PATH%"

echo.
echo Modos:
echo   [1] Nome + porta 8000  (predefinido)
echo   [2] Nome SEM porta - http://pdf.intranet  (instala proxy Caddy na porta 80)
echo.
set /p MODO="Escolha 1 ou 2 (Enter = 1): "
if "%MODO%"=="2" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar-intranet.ps1" -ComProxy -SemPausa
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar-intranet.ps1" -SemPausa
)
set "PS_EXIT=%ERRORLEVEL%"
if not "%PS_EXIT%"=="0" (
  echo.
  echo [ERRO] A preparacao falhou com codigo %PS_EXIT%.
  pause
  exit /b %PS_EXIT%
)
pause
exit /b 0
