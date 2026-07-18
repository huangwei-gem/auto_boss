@echo off
title Boss 直聘 · 自动投递 Web 版
cd /d "%~dp0web_app"
echo ========================================
echo  Boss 直聘 · 自动投递  Web 版
echo  启动地址: http://127.0.0.1:5000
echo ========================================
start http://127.0.0.1:5000
call "..\boss自动投简历\.venv\Scripts\python" server.py
pause
