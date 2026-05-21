@echo off
REM Grocery Optimizer Launch Convenience Wrapper
REM Double-click this file to launch the application

setlocal enabledelayedexpansion

REM Check if PowerShell is available
where powershell >nul 2>nul
if errorlevel 1 (
    echo ERROR: PowerShell not found
    pause
    exit /b 1
)

REM Launch the PowerShell script
echo.
echo Launching Grocery Optimizer...
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0launch.ps1" %*

REM If the script failed, pause so user can see the error
if errorlevel 1 (
    echo.
    echo Launch failed. Press any key to close...
    pause
)
