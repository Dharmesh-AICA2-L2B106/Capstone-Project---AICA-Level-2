@echo off
setlocal EnableDelayedExpansion
title Clientdesk AI - Installation Setup

echo ======================================================================
echo             Clientdesk AI - Practice Workflow Management
echo                   Installation & Desktop Setup
echo ======================================================================
echo.
echo Notice: This installation provides a 14-Day Free Evaluation Trial.
echo After 14 calendar days, the system will lock automatically.
echo.

set "SOURCE_EXE=%~dp0dist\ClientdeskAI.exe"
if not exist "%SOURCE_EXE%" (
    set "SOURCE_EXE=%~dp0ClientdeskAI.exe"
)

if not exist "%SOURCE_EXE%" (
    echo [ERROR] Could not find ClientdeskAI.exe!
    echo Please make sure ClientdeskAI.exe is present in the dist\ folder.
    pause
    exit /b 1
)

set "TARGET_DIR=%LOCALAPPDATA%\Programs\ClientdeskAI"
echo [*] Creating installation directory at:
echo     %TARGET_DIR%
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

echo [*] Copying ClientdeskAI.exe into installation folder...
copy /Y "%SOURCE_EXE%" "%TARGET_DIR%\ClientdeskAI.exe" >nul
if %errorlevel% neq 0 (
    echo [ERROR] Failed to copy executable to %TARGET_DIR%.
    pause
    exit /b 1
)

echo [*] Creating Desktop and Start Menu Shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$wsh = New-Object -ComObject WScript.Shell; " ^
    "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
    "$startMenu = [Environment]::GetFolderPath('Programs'); " ^
    "$exePath = '%TARGET_DIR%\ClientdeskAI.exe'; " ^
    "$scDesktop = $wsh.CreateShortcut(\"$desktop\Clientdesk AI.lnk\"); " ^
    "$scDesktop.TargetPath = $exePath; " ^
    "$scDesktop.WorkingDirectory = '%TARGET_DIR%'; " ^
    "$scDesktop.Description = 'Clientdesk AI - Compliance & Practice Portal'; " ^
    "$scDesktop.Save(); " ^
    "$scStart = $wsh.CreateShortcut(\"$startMenu\Clientdesk AI.lnk\"); " ^
    "$scStart.TargetPath = $exePath; " ^
    "$scStart.WorkingDirectory = '%TARGET_DIR%'; " ^
    "$scStart.Description = 'Clientdesk AI - Compliance & Practice Portal'; " ^
    "$scStart.Save();"

echo.
echo ======================================================================
echo                INSTALLATION COMPLETED SUCCESSFULLY!
echo ======================================================================
echo.
echo  - Installed to: %TARGET_DIR%\ClientdeskAI.exe
echo  - Desktop shortcut: "Clientdesk AI.lnk" created on Desktop
echo  - Start Menu shortcut: "Clientdesk AI.lnk" created in Start Menu
echo.
echo  Default Login Credentials:
echo   - User ID:  admin
echo   - Password: admin
echo   - Note: Administrator can add staff accounts with assigned passwords in Settings.
echo.
echo  Evaluation Policy:
echo   - 14 Days Free Trial access is active from the date of first launch.
echo   - After 14 days, the system will automatically lock.
echo.

set /p LAUNCH="Do you want to launch Clientdesk AI now? (Y/N): "
if /i "%LAUNCH%"=="Y" (
    start "" "%TARGET_DIR%\ClientdeskAI.exe"
)

echo Thank you for installing Clientdesk AI.
exit /b 0
