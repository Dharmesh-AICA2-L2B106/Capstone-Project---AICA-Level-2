@echo off
rem ======================================================================
rem  PDF Play Station 2.0 - launcher
rem  Double-click this file to start the application.
rem  First run: creates a private Python environment (.venv) in this folder
rem  and installs the required components from requirements.txt (needs
rem  internet once). Later runs start immediately and work fully offline;
rem  components are only reinstalled when requirements.txt changes.
rem  No administrator rights are needed; nothing is installed system-wide.
rem ======================================================================
setlocal EnableExtensions DisableDelayedExpansion
title PDF Play Station - Launcher

rem Work from the folder that contains this file (paths may contain spaces or &).
cd /d "%~dp0"
if errorlevel 1 goto :no_folder

set "VENV_DIR=.venv"
set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PYW=.venv\Scripts\pythonw.exe"

echo.
echo  ==============================================
echo     PDF Play Station 2.0
echo     by CA Aditya Mundada
echo  ==============================================
echo.

if not exist "PDF_Play_Station.py" goto :missing_files
if not exist "requirements.txt" goto :missing_files

rem ---------------------------------------------------------------- venv
if not exist "%VENV_PY%" goto :create_venv
"%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto :check_deps
echo  [!] The existing private Python environment does not work any more.
echo      It will be recreated.
rmdir /s /q "%VENV_DIR%"

:create_venv
call :find_python
if not defined PY_CMD goto :no_python
echo  [1/3] Creating a private Python environment (first run only)...
echo        Using: %PY_VERSION%
%PY_CMD% -m venv "%VENV_DIR%"
if errorlevel 1 goto :venv_failed
if not exist "%VENV_PY%" goto :venv_failed

rem ---------------------------------------------------------------- packages
:check_deps
echo  [2/3] Checking required components...
"%VENV_PY%" "tools\check_requirements.py" check
if not errorlevel 1 goto :launch

echo        Installing required components. This needs an internet connection
echo        the first time and can take a few minutes. Please wait...
echo.
if exist "wheels\" (
    echo        Using the local "wheels" folder - no internet needed.
    "%VENV_PY%" -m pip install --disable-pip-version-check --no-input --no-index --find-links "wheels" -r "requirements.txt"
) else (
    "%VENV_PY%" -m pip install --disable-pip-version-check --no-input -r "requirements.txt"
)
if errorlevel 1 goto :pip_failed
"%VENV_PY%" "tools\check_requirements.py" imports
if errorlevel 1 goto :pip_failed
"%VENV_PY%" "tools\check_requirements.py" stamp
echo.
echo        Components installed successfully.

rem ---------------------------------------------------------------- start
:launch
echo  [3/3] Starting PDF Play Station...
if exist "%VENV_PYW%" (
    start "" "%VENV_PYW%" "PDF_Play_Station.py"
) else (
    start "" "%VENV_PY%" "PDF_Play_Station.py"
)
if errorlevel 1 goto :start_failed
endlocal
exit /b 0

rem ======================================================================
rem  Helpers
rem ======================================================================
:find_python
rem Looks for a compatible 64-bit Python (3.10 - 3.14): the "py" launcher
rem first, then "python" / "python3" on PATH. The free-threaded build
rem (python3.14t) is not used.
set "PY_CMD="
set "PY_VERSION="
for %%C in ("py -3.14" "py -3.13" "py -3.12" "py -3.11" "py -3.10" "py -3" "python" "python3") do (
    if not defined PY_CMD (
        %%~C -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>&1 && set "PY_CMD=%%~C"
    )
)
if defined PY_CMD for /f "delims=" %%V in ('%PY_CMD% --version 2^>^&1') do set "PY_VERSION=%%V"
exit /b 0

:no_folder
echo  [ERROR] Could not open the application folder.
goto :fail

:missing_files
echo  [ERROR] Application files are missing (PDF_Play_Station.py or requirements.txt).
echo          Make sure you copied the complete "PDF Play Station 2.0" folder.
goto :fail

:no_python
echo  [ERROR] A compatible Python installation was not found.
echo.
echo          PDF Play Station needs Python 3.10 to 3.14 (64-bit).
echo          1. Download Python from https://www.python.org/downloads/windows/
echo          2. During setup tick "Add python.exe to PATH" (and keep the "py launcher").
echo          3. Run this file again.
goto :fail

:venv_failed
echo  [ERROR] The private Python environment could not be created in:
echo          "%CD%\%VENV_DIR%"
echo          Check that this folder is not read-only, then run this file again.
goto :fail

:pip_failed
echo.
echo  [ERROR] The required components could not be installed.
echo          - Check your internet connection (a proxy or firewall may block
echo            access to pypi.org).
echo          - Free disk space is needed (about 500 MB).
echo          - Then run this file again; it will resume where it stopped.
echo          The messages above show the exact problem.
goto :fail

:start_failed
echo  [ERROR] The application could not be started.
echo          See the logs folder for details.
goto :fail

:fail
echo.
echo  Press any key to close this window.
pause >nul
endlocal
exit /b 1
