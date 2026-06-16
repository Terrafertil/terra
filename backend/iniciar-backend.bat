@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Ambiente virtual nao encontrado. Criando .venv...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERRO] Falha ao criar ambiente virtual. Verifique se o Python esta instalado.
    pause
    exit /b 1
  )
)

if not exist "run.py" (
  echo [ERRO] Ficheiro run.py nao encontrado em backend\
  pause
  exit /b 1
)

echo [INFO] Atualizando dependencias do backend...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
  echo [ERRO] Falha ao instalar dependencias do backend.
  pause
  exit /b 1
)

echo Iniciando backend...
call ".venv\Scripts\activate.bat"
python run.py

pause
