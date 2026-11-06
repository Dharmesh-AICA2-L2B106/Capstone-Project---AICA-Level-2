@echo off
cd /d "%~dp0"
py -3 --version >nul 2>&1
if errorlevel 1 goto try_python
py -3 life_planner.py
if errorlevel 1 pause
exit /b
:try_python
python --version >nul 2>&1
if errorlevel 1 goto missing
python life_planner.py
if errorlevel 1 pause
exit /b
:missing
echo Please install Python 3 from https://www.python.org/downloads/windows/
echo During installation enable Add Python to PATH and Tcl/Tk support.
echo Then double-click this launcher again.
pause
