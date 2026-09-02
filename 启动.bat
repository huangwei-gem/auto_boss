@echo off
chcp 65001 >nul 2>&1
title Boss直聘自动投递 - Web Server
cd /d "%~dp0"

echo ========================================
echo   Boss直聘 · 自动投递  Web 版
echo   ========================================
echo.

:: ── 检查 Python ──
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo   Python: %%i

:: ── 创建虚拟环境（如果不存在） ──
if not exist "venv\Scripts\python.exe" (
    echo   创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo   [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo   ✅ 虚拟环境创建完成
)

:: ── 激活虚拟环境并安装依赖 ──
call venv\Scripts\activate.bat

echo   升级 pip...
pip install --upgrade pip -q 2>nul

echo   安装依赖...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo   [错误] 安装失败，请检查网络连接
    pause
    exit /b 1
)
echo   ✅ 依赖安装完成

:: ── 验证安装 ──
echo   验证环境...
python -c "import sys; sys.path.insert(0, 'app'); from browser_launcher import launch_browser; from bot_core import BotCore; from app.server import app; print('  ✅ 环境验证通过')"
if errorlevel 1 (
    echo   [错误] 验证失败
    pause
    exit /b 1
)

:: ── 启动 ──
echo   ========================================
echo   🚀 启动地址: http://127.0.0.1:5000
echo   ========================================
echo.
start "" "http://127.0.0.1:5000"
python run.py

echo.
echo [服务器已停止]
pause
