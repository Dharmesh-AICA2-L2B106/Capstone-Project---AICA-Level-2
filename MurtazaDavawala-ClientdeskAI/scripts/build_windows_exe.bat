@echo off
echo ========================================================
echo  Clientdesk AI - Windows Standalone Executable Builder
echo ========================================================

set PYTHON_CMD=.\.venv\Scripts\python.exe
if not exist %PYTHON_CMD% (
    echo [ERROR] Virtual environment python not found at %PYTHON_CMD%!
    echo Please make sure the .venv directory is configured.
    exit /b 1
)

echo [1/3] Verifying test suite before building...
%PYTHON_CMD% verify_clientdesk_ai.py
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Verification tests failed! Aborting build.
    exit /b %ERRORLEVEL%
)

echo [2/3] Building executable using PyInstaller...
%PYTHON_CMD% -m PyInstaller ^
    --name="Clientdesk_AI" ^
    --onedir ^
    --windowed ^
    --clean ^
    --noconfirm ^
    --add-data "src;src" ^
    --hidden-import "PyQt6" ^
    --hidden-import "PyQt6.QtCore" ^
    --hidden-import "PyQt6.QtGui" ^
    --hidden-import "PyQt6.QtWidgets" ^
    --hidden-import "openpyxl" ^
    --hidden-import "sqlite3" ^
    run_app.py

if %ERRORLEVEL% neq 0 (
    echo [ERROR] PyInstaller build failed!
    exit /b %ERRORLEVEL%
)

echo [3/3] Build completed successfully!
echo Executable is located in dist\Clientdesk_AI\Clientdesk_AI.exe
echo ========================================================
