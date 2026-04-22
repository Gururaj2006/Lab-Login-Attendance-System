@echo off
setlocal

cd /d "%~dp0"

rem Keep server sync enabled so all PCs can refresh the same latest student list.
set LAB_ENABLE_SERVER_SYNC=1

if not exist "%~dp0login.exe" (
    echo login.exe was not found in this folder.
    pause
    exit /b 1
)

start "" "%~dp0login.exe"

endlocal
