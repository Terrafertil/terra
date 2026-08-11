@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "NEED_INSTALL=0"
set "LOCK_HASH="

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Ambiente virtual nao encontrado. Criando .venv...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERRO] Falha ao criar ambiente virtual. Verifique se o Python esta instalado.
    pause
    exit /b 1
  )
  set "NEED_INSTALL=1"
)

if not exist "run.py" (
  echo [ERRO] Ficheiro run.py nao encontrado em backend\
  pause
  exit /b 1
)

if exist "requirements.lock" (
  for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath 'requirements.lock').Hash.ToLowerInvariant()"`) do set "LOCK_HASH=%%H"
  if not defined LOCK_HASH (
    echo [ERRO] Nao foi possivel calcular o hash de requirements.lock.
    pause
    exit /b 1
  )
  if not exist ".venv\.requirements-lock.sha256" (
    set "NEED_INSTALL=1"
  ) else (
    set /p "INSTALLED_LOCK_HASH=" < ".venv\.requirements-lock.sha256"
    if /I not "!INSTALLED_LOCK_HASH!"=="!LOCK_HASH!" set "NEED_INSTALL=1"
  )
)

if "!NEED_INSTALL!"=="0" (
  ".venv\Scripts\python.exe" -c "import fastapi, uvicorn, sqlalchemy, alembic, pydantic, pydantic_settings, email_validator, multipart, dotenv, pdfplumber, pypdf, passlib, bcrypt, jwt, cryptography, watchdog, jinja2, fitz, pytesseract, PIL" >nul 2>nul
  if errorlevel 1 set "NEED_INSTALL=1"
)

if "!NEED_INSTALL!"=="0" (
  ".venv\Scripts\python.exe" -m pip check >nul 2>nul
  if errorlevel 1 set "NEED_INSTALL=1"
)

if "!NEED_INSTALL!"=="1" (
  echo [INFO] Instalando dependencias do backend...
  if exist "requirements.lock" (
    ".venv\Scripts\python.exe" -m pip install --require-hashes -r requirements.lock
  ) else (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  )
  if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias do backend.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip check
  if errorlevel 1 (
    echo [ERRO] Dependencias instaladas, mas o ambiente ficou inconsistente.
    pause
    exit /b 1
  )
  if defined LOCK_HASH > ".venv\.requirements-lock.sha256" echo(!LOCK_HASH!
)

echo Iniciando backend...
call ".venv\Scripts\activate.bat"
python run.py

pause
