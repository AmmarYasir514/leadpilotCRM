@echo off
rem LeadPilot web scheduler launcher. Runs "php artisan schedule:run" once against the preview database.
rem It only creates "send it yourself" follow-up reminders. It never sends anything to a client.
setlocal
set "DB_CONNECTION=sqlite"
set "DB_DATABASE=%LOCALAPPDATA%\LeadPilotToolchain\leadpilot-preview.sqlite"
set "PHP_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Packages\PHP.PHP.8.4_Microsoft.Winget.Source_8wekyb3d8bbwe\php.exe"
cd /d "%~dp0.."
if not exist "%PHP_EXE%" (
  echo [%date% %time%] ERROR: php.exe not found at "%PHP_EXE%">> "storage\logs\scheduler.log"
  exit /b 9009
)
echo [%date% %time%] schedule:run>> "storage\logs\scheduler.log"
"%PHP_EXE%" artisan schedule:run >> "storage\logs\scheduler.log" 2>&1
exit /b %ERRORLEVEL%
