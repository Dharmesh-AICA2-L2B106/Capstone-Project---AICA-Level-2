@echo off
setlocal EnableDelayedExpansion
echo ========================================================
echo  Starting Clientdesk AI (Local Desktop Edition)
echo ========================================================
echo.

cd /d "%~dp0"

:: 1. Check for local virtual environment in current folder
if exist ".\.venv\Scripts\python.exe" (
    echo [*] Found local virtual environment.
    ".\.venv\Scripts\python.exe" run_app.py
    goto :end
)

:: 2. Check for virtual environment in parent directory
if exist "..\.venv\Scripts\python.exe" (
    echo [*] Found virtual environment in parent folder.
    "..\.venv\Scripts\python.exe" run_app.py
    goto :end
)

:: 3. Check for standalone compiled executable
if exist ".\dist\ClientdeskAI.exe" (
    echo [*] Launching standalone executable from dist\...
    start "" ".\dist\ClientdeskAI.exe"
    goto :end
)

if exist "..\dist\ClientdeskAI.exe" (
    echo [*] Launching standalone executable from parent dist\...
    start "" "..\dist\ClientdeskAI.exe"
    goto :end
)

:: 4. Check for Python installed on system PATH
where python >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Using system Python from PATH...
    python run_app.py
    goto :end
)

:: 5. Check for Windows Python launcher (py.exe)
where py >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Using Windows Python Launcher (py)...
    py -3 run_app.py
    goto :end
)

:: 6. Check common user AppData Python installation paths
if exist "%LOCALAPPDATA%\Programs\Python\Python315\python.exe" (
    echo [*] Found Python 3.15 in AppData.
    "%LOCALAPPDATA%\Programs\Python\Python315\python.exe" run_app.py
    goto :end
)

if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
    echo [*] Found Python 3.14 in AppData.
    "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" run_app.py
    goto :end
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    echo [*] Found Python 3.13 in AppData.
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" run_app.py
    goto :end
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    echo [*] Found Python 3.12 in AppData.
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" run_app.py
    goto :end
)

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    echo [*] Found Python 3.11 in AppData.
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" run_app.py
    goto :end
)

if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    echo [*] Found Python 3.10 in AppData.
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" run_app.py
    goto :end
)

:: 7. Check standard root C:\Python paths
if exist "C:\Python315\python.exe" (
    "C:\Python315\python.exe" run_app.py
    goto :end
)
if exist "C:\Python314\python.exe" (
    "C:\Python314\python.exe" run_app.py
    goto :end
)
if exist "C:\Python313\python.exe" (
    "C:\Python313\python.exe" run_app.py
    goto :end
)
if exist "C:\Python312\python.exe" (
    "C:\Python312\python.exe" run_app.py
    goto :end
)

echo [ERROR] No Python runtime or ClientdeskAI.exe was found!
echo.
echo To run from source:
echo   1. Please ensure Python 3.10+ is installed and added to PATH, OR
echo   2. Run: python -m venv .venv ^&^& .\.venv\Scripts\pip install -r requirements.txt
echo.
echo Or run the standalone Windows installer:
echo   Double-click "Install_ClientdeskAI.bat"
echo.

:end
if %errorlevel% neq 0 (
    echo.
    echo Application exited with code %errorlevel%.
)
pause
