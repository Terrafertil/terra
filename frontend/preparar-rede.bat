@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Preparar rede - Terra Fertil

REM Node no PATH (nvm / instalacao padrao)
if defined NVM_SYMLINK if exist "%NVM_SYMLINK%\npm.cmd" set "PATH=%NVM_SYMLINK%;%PATH%"
if exist "C:\nvm4w\nodejs\npm.cmd" set "PATH=C:\nvm4w\nodejs;%PATH%"
if exist "%ProgramFiles%\nodejs\npm.cmd" set "PATH=%ProgramFiles%\nodejs;%PATH%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar-rede.ps1" %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
