@echo off
cd /d "%~dp0"
echo Installing requirements (first time only takes a minute)...
python -m pip install -r requirements.txt
echo.
python main.py
pause
