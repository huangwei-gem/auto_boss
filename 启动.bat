@echo off
chcp 65001 >/dev/null 2>&1
title Boss Auto Apply - Web Server
cd /d "%~dp0"

echo ========================================
echo   Boss Auto Apply - Web Server
echo   URL: http://127.0.0.1:5000
echo ========================================
echo.

start "" "http://127.0.0.1:5000"

python -c "import sys,io,os; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8'); sys.path.insert(0,os.getcwd()); from web_app.server import app,socketio; socketio.run(app,host='127.0.0.1',port=5000,debug=False,allow_unsafe_werkzeug=True)"

echo.
echo [Server stopped]
pause
