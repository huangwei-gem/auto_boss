@echo off
chcp 65001 >nul
cd /d "%~dp0web_app"
echo ==============================================
echo   Boss直聘 · 自动投递  Web
echo   http://127.0.0.1:5000
echo ==============================================
start http://127.0.0.1:5000
call "%~dp0venv\Scripts\python" server.py
pause
