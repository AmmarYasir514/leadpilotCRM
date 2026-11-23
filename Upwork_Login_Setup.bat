@echo off
cd /d "%~dp0"
python -c "import keyring" >nul 2>nul || python -m pip install --user keyring
python upwork_credentials.py
if errorlevel 1 pause
