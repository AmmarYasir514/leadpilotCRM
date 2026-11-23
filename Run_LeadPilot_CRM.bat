@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 leadpilot_crm.py) else (python leadpilot_crm.py)
if errorlevel 1 pause
