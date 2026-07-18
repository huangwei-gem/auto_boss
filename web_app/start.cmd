@echo off
cd /d "%~dp0"
echo 安装依赖...
call .venv\Scripts\pip install -r requirements.txt
echo 启动 Boss 直聘 · 自动投递 Web 版
start http://127.0.0.1:5000
call .venv\Scripts\python server.py
pause
