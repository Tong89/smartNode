@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting separated backend on http://127.0.0.1:5000
echo Frontend: http://127.0.0.1:5000/frontend/
d:\ProgramData\anaconda\envs\gunradio\python.exe backend\app.py
pause
