@echo off
setlocal

set "SOURCE_DIR=%~dp0"
set "TARGET_DIR=C:\LabLoginSystem"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_FILE=%STARTUP_DIR%\LabLoginSystem Startup.bat"

echo Installing Lab Login System...

if not exist "%SOURCE_DIR%login.exe" (
    echo login.exe not found in %SOURCE_DIR%
    exit /b 1
)

if not exist "%SOURCE_DIR%lab.db" (
    echo lab.db not found in %SOURCE_DIR%
    exit /b 1
)

if not exist "%SOURCE_DIR%start_student_login.bat" (
    echo start_student_login.bat not found in %SOURCE_DIR%
    exit /b 1
)

taskkill /IM login.exe /F >nul 2>&1

if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

copy /Y "%SOURCE_DIR%login.exe" "%TARGET_DIR%\login.exe" >nul
copy /Y "%SOURCE_DIR%lab.db" "%TARGET_DIR%\lab.db" >nul
copy /Y "%SOURCE_DIR%start_student_login.bat" "%TARGET_DIR%\start_student_login.bat" >nul

if not exist "%STARTUP_DIR%" mkdir "%STARTUP_DIR%"

(
    echo @echo off
    echo cd /d "%TARGET_DIR%"
    echo call "%TARGET_DIR%\start_student_login.bat"
) > "%STARTUP_FILE%"

start "" "%TARGET_DIR%\start_student_login.bat"

echo Installation complete.
echo Files installed to %TARGET_DIR%
echo Startup launcher created at %STARTUP_FILE%

endlocal
