@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Starting SmartNode backend...
echo Frontend: http://127.0.0.1:5000/frontend/

python backend\app.py
pause
