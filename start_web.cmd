@echo off
rem =====================================================
rem  Boss直聘 AI 自动投递助手 - 一键启动
rem  自动创建虚拟环境 core\.venv、安装依赖并启动 Web 服务
rem  访问地址: http://127.0.0.1:5000
rem  用法:
rem    start_web.cmd          正常启动（自动打开浏览器）
rem    start_web.cmd test     不打开浏览器、结束后不暂停（用于测试/脚本调用）
rem =====================================================
setlocal
set "ROOT=%~dp0"
set "VENV=%ROOT%core\.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "REQ=%ROOT%web_app\requirements.txt"
set "URL=http://127.0.0.1:5000"

echo ========================================
echo  Boss直聘 AI 自动投递助手
echo  %URL%
echo ========================================

rem ---- 1. 定位 Python 解释器 ----
set "PY=python"
%PY% -c "pass" >nul 2>nul
if errorlevel 1 set "PY=py -3"
%PY% -c "pass" >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Python，请先安装 Python 3.9+ 再运行
  pause
  exit /b 1
)

rem ---- 2. 创建虚拟环境（如不存在）----
if exist "%VPY%" (
  echo [1/3] 虚拟环境已存在: core\.venv
) else (
  echo [1/3] 正在创建虚拟环境 core\.venv ...
  %PY% -m venv "%VENV%"
  if errorlevel 1 (
    echo [错误] 创建虚拟环境失败
    pause
    exit /b 1
  )
)

rem ---- 3. 安装依赖（如缺失）----
"%VPY%" -c "import flask, flask_socketio, DrissionPage" >nul 2>nul
if errorlevel 1 (
  echo [2/3] 正在安装依赖 ...
  "%VPY%" -m pip install -r "%REQ%" -i https://pypi.tuna.tsinghua.edu.cn/simple
  if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
  )
) else (
  echo [2/3] 依赖已就绪
)

rem ---- 4. 启动 Web 服务 ----
if /i not "%1"=="test" (
  start "" /b "%VPY%" -c "import time,webbrowser; time.sleep(3); webbrowser.open('%URL%')"
)
echo [3/3] 启动 Web 服务，浏览器访问 %URL%
cd /d "%ROOT%web_app"
"%VPY%" server.py

if /i not "%1"=="test" pause
exit /b 0
