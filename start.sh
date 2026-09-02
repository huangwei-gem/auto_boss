#!/bin/bash
# Boss直聘自动投递 · macOS/Linux 启动脚本
# 使用方法: chmod +x start.sh && ./start.sh

cd "$(dirname "$0")"

# ── 检查 Python ──
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "❌ 未找到 Python，请先安装 Python 3.8+"
    echo "   下载地址: https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
echo "  Boss 直聘 · 自动投递  Web 版"
echo "  Python: $PY_VERSION"
echo "  ========================================"

# ── 创建虚拟环境（如果不存在） ──
if [ ! -d "venv" ]; then
    echo "  创建虚拟环境..."
    if ! $PYTHON -m venv venv 2>/dev/null; then
        echo "  ❌ 创建虚拟环境失败"
        echo "  💡 尝试安装 python3-venv: sudo apt install python3-venv"
        exit 1
    fi
    echo "  ✅ 虚拟环境创建完成"
fi

# ── 激活虚拟环境 ──
source venv/bin/activate

# ── 升级 pip ──
echo "  升级 pip..."
pip install --upgrade pip -q 2>/dev/null

# ── 安装依赖 ──
echo "  安装依赖..."
if ! pip install -r requirements.txt -q; then
    echo "  ❌ 安装失败，请检查网络连接"
    exit 1
fi
echo "  ✅ 依赖安装完成"

# ── 验证安装 ──
echo "  验证环境..."
python3 -c "
import sys
sys.path.insert(0, 'app')
try:
    from browser_launcher import launch_browser, _find_chrome_path
    from bot_core import BotCore
    from app.server import app
    print('  ✅ 环境验证通过')
except Exception as e:
    print(f'  ❌ 验证失败: {e}')
    sys.exit(1)
" || exit 1

# ── 启动 ──
echo "  ========================================"
echo "  🚀 启动地址: http://127.0.0.1:5000"
echo "  ========================================"
python run.py
