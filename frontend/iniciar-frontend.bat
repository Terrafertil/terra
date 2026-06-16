@echo off
setlocal EnableExtensions

cd /d "%~dp0"
title Terra Fertil - Frontend

REM Duplo clique no Explorer muitas vezes nao carrega o PATH do nvm/Node — tentamos localizar.
if defined NVM_SYMLINK if exist "%NVM_SYMLINK%\npm.cmd" set "PATH=%NVM_SYMLINK%;%PATH%"
if exist "C:\nvm4w\nodejs\npm.cmd" set "PATH=C:\nvm4w\nodejs;%PATH%"
if exist "%ProgramFiles%\nodejs\npm.cmd" set "PATH=%ProgramFiles%\nodejs;%PATH%"
if exist "%LocalAppData%\Programs\node\npm.cmd" set "PATH=%LocalAppData%\Programs\node;%PATH%"

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERRO] npm nao encontrado. Instale Node.js LTS ou abra este .bat a partir de um terminal onde "npm" funciona.
  echo        https://nodejs.org/
  pause
  exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo [ERRO] node nao encontrado no PATH.
  pause
  exit /b 1
)

if not exist "package.json" (
  echo [ERRO] package.json nao encontrado em:
  echo        %CD%
  pause
  exit /b 1
)

echo [INFO] A preparar .env para acesso na rede (IP + API)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar-rede.ps1" -SemPausa -SkipBuild -SkipFirewall
if errorlevel 1 (
  echo [AVISO] preparar-rede.ps1 falhou — a usar .env existente, se houver.
  if not exist ".env" if exist ".env.example" copy /Y ".env.example" ".env" >nul
)

if not exist "node_modules" (
  echo [INFO] Primeira execucao: a instalar dependencias...
  call npm install
  if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias do frontend.
    pause
    exit /b 1
  )
)

REM Porta 5173 ja ocupada (outra instancia do Vite)?
netstat -ano | findstr ":5173" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [AVISO] A porta 5173 ja esta em uso — provavelmente o frontend ja esta a correr.
  echo         Abra http://localhost:5173 ou http://192.168.1.5:5173
  echo         Para parar: feche a janela do Vite ou termine o processo na porta 5173.
  pause
  exit /b 1
)

echo.
echo ========================================
echo   Frontend - Sistema de Envio de Apolices
echo ========================================
echo   Node:  & node --version
echo   Pasta: %CD%
if exist ".env" (
  echo   .env:  encontrado ^(VITE_API_URL usado pelo Vite^)
) else (
  echo   .env:  ausente
)
echo.
echo   Apos iniciar, abra no browser:
echo     Neste PC:     http://localhost:5173
echo     Outros na rede: http://IP-DESTE-SERVIDOR:5173
echo   ^(O backend deve estar a correr na porta 8000^)
echo ========================================
echo.

call npm run dev
set EXITCODE=%ERRORLEVEL%

if not %EXITCODE%==0 (
  echo.
  echo [ERRO] O frontend terminou com codigo %EXITCODE%.
  echo        Se a porta estiver ocupada, feche a outra instancia e tente de novo.
)

pause
exit /b %EXITCODE%
