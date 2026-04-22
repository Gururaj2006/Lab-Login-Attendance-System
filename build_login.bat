@echo off
setlocal

cd /d "%~dp0"
set "PYTHON_EXE=python"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)

echo Preparing local database...
"%PYTHON_EXE%" database.py
"%PYTHON_EXE%" add_students.py
"%PYTHON_EXE%" sync_local_students.py
if errorlevel 1 goto :fail

echo Building login executable...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean login.spec
if errorlevel 1 goto :fail

echo Build complete.
echo Output: dist\login.exe
goto :end

:fail
echo Build failed.
exit /b 1

:end
endlocal
