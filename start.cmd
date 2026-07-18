@echo off
cd /d "%~dp0web_app"
echo ========================================
echo  Boss Auto Apply - Web
echo  http://127.0.0.1:5000
echo ========================================
start http://127.0.0.1:5000
call "%~dp0core\.venv\Scripts\python" server.py
pause
