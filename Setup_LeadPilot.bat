@echo off
setlocal
title LeadPilot CRM Setup
cd /d "%~dp0"

echo ==========================================
echo       LeadPilot CRM - Windows Setup
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 goto CHECK_TK

where python >nul 2>nul
if %errorlevel%==0 goto CHECK_TK

echo Python was not found on this computer.
echo Trying to install Python 3.12 using Windows Package Manager...
where winget >nul 2>nul
if errorlevel 1 goto MANUAL

winget install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto MANUAL

echo.
echo Python installation command completed.
echo Close this window and open Setup_LeadPilot.bat again if Python is not detected.
pause
exit /b 0

:CHECK_TK
echo Checking Python and Tkinter...
py -3 -c "import tkinter, sqlite3" >nul 2>nul
if errorlevel 1 python -c "import tkinter, sqlite3" >nul 2>nul
if errorlevel 1 goto TK_ERROR

echo.
echo Setup check passed. Launching LeadPilot CRM...
call Run_LeadPilot_CRM.bat
exit /b 0

:TK_ERROR
echo Python is installed, but Tkinter is missing or unavailable.
echo Please reinstall Python from python.org and ensure Tcl/Tk support is selected.
pause
exit /b 1

:MANUAL
echo.
echo Automatic installation is unavailable on this computer.
echo Please install Python 3.10 or newer from:
echo https://www.python.org/downloads/windows/
echo During installation, enable "Add Python to PATH".
echo Then run Setup_LeadPilot.bat again.
echo.
pause
exit /b 1
