"""重启 Flask 服务器 - 杀掉所有占用 5000 端口的进程（跨平台）"""
import os
import sys
import signal
import subprocess
import time
import platform

_IS_WINDOWS = platform.system().lower() == "windows"
PORT = 5000


def _find_pids_windows():
    """Windows: 查找占用端口的 PID"""
    result = subprocess.run(
        f'netstat -ano | findstr :{PORT}',
        shell=True, capture_output=True, text=True
    )
    pids = set()
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 5 and parts[1].endswith(f':{PORT}') and 'LISTENING' in line:
            pids.add(parts[-1])
    return pids


def _find_pids_unix():
    """macOS/Linux: 查找占用端口的 PID"""
    # 尝试 lsof
    try:
        result = subprocess.run(
            ['lsof', '-ti', f'tcp:{PORT}'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return set(result.stdout.strip().split())
    except FileNotFoundError:
        pass

    # 备选: fuser
    try:
        result = subprocess.run(
            ['fuser', f'{PORT}/tcp'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return set(result.stdout.strip().split())
    except FileNotFoundError:
        pass

    return set()


def _find_pids():
    """查找占用端口的 PID（跨平台）"""
    if _IS_WINDOWS:
        return _find_pids_windows()
    return _find_pids_unix()


def main():
    pids = _find_pids()
    print(f"找到 {len(pids)} 个监听 {PORT} 端口的进程: {pids}")

    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
            print(f"  已终止 PID {pid}")
        except Exception as e:
            print(f"  终止 PID {pid} 失败: {e}")

    time.sleep(2)

    # 启动新服务
    if _IS_WINDOWS:
        python_path = os.path.join("venv", "Scripts", "python.exe")
    else:
        python_path = os.path.join("venv", "bin", "python")

    server_path = os.path.dirname(os.path.abspath(__file__))

    kwargs = {
        "cwd": server_path,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if _IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen([python_path, "run.py"], **kwargs)
    print("✓ 新服务器已启动")


if __name__ == "__main__":
    main()
