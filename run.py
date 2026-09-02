"""Boss直聘自动投递 · Web 入口（跨平台版）

启动：python run.py
访问：http://127.0.0.1:5000

支持平台：Windows / macOS / Linux
"""
import os
import sys
import platform

# 把 app/ 加入 path，让 from config / from bot_core 能直接 import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

from app.server import app, socketio

if __name__ == "__main__":
    print("  Boss 直聘 · 自动投递  Web 版（跨平台版）")
    print(f"  平台: {platform.system()} {platform.machine()}")
    print(f"  Python: {platform.python_version()}")
    print("  启动地址: http://127.0.0.1:5000")
    print("  " + "=" * 40)
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)
