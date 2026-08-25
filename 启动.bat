@echo off
chcp 65001 >nul 2>&1
title Boss Auto Apply - Web Server
cd /d "%~dp0"

echo ========================================
echo   Boss Auto Apply - Web Server
echo   URL: http://127.0.0.1:5000
echo ========================================
echo.

start "" "http://127.0.0.1:5000"

"venv\Scripts\python.exe" run.py

echo.
echo [Server stopped]
pause
