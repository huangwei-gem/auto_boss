"""重启 Flask 服务器 - 杀掉所有占用 5000 端口的进程"""
import os, signal, subprocess, time

# 查找占用 5000 端口的进程
result = subprocess.run(
    'netstat -ano | findstr :5000',
    shell=True, capture_output=True, text=True
)
pids = set()
for line in result.stdout.splitlines():
    parts = line.strip().split()
    if len(parts) >= 5 and parts[1].endswith(':5000') and 'LISTENING' in line:
        pids.add(parts[-1])

print(f"找到 {len(pids)} 个监听 5000 端口的进程: {pids}")

for pid in pids:
    try:
        os.kill(int(pid), signal.SIGTERM)
        print(f"  已终止 PID {pid}")
    except Exception as e:
        print(f"  终止 PID {pid} 失败: {e}")

time.sleep(2)

# 启动新服务
server_path = os.path.join(os.path.dirname(__file__), "web_app", "server.py")
subprocess.Popen(
    ["venv/Scripts/python", server_path],
    cwd=os.path.dirname(__file__),
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print("✓ 新服务器已启动")
