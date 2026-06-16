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
)

if defined NVM_SYMLINK if exist "%NVM_SYMLINK%\npm.cmd" set "PATH=%NVM_SYMLINK%;%PATH%"
if exist "C:\nvm4w\nodejs\npm.cmd" set "PATH=C:\nvm4w\nodejs;%PATH%"

echo.
echo Modos:
echo   [1] Nome + portas 5173/8000  (predefinido)
echo   [2] Nome SEM porta - http://pdf.intranet  (instala proxy Caddy na porta 80)
echo.
set /p MODO="Escolha 1 ou 2 (Enter = 1): "
if "%MODO%"=="2" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar-intranet.ps1" -ComProxy
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar-intranet.ps1"
)
pause
