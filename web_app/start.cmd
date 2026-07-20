@echo off
cd /d "%~dp0"
echo ========================================
echo  Boss Auto Apply - Web
echo  http://127.0.0.1:5000
echo ========================================
start http://127.0.0.1:5000
call "%~dp0..\core\.venv\Scripts\python" server.py
pause
