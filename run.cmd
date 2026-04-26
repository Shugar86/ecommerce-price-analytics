@echo off
setlocal

REM Простая обёртка для запуска PowerShell-скрипта без плясок с ExecutionPolicy.
REM Примеры:
REM   run.cmd up
REM   run.cmd up -Build
REM   run.cmd logs -Follow
REM   run.cmd logs -Service bot -Follow

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
exit /b %ERRORLEVEL%


