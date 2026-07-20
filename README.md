# Boss 直聘 · 自动投递

基于 DrissionPage 的 Boss 直聘自动投递 **Web 版**。

## 快速启动

```bash
start.cmd     # 双击
# 浏览器打开 http://127.0.0.1:5000
```

## 项目结构

```
├── web_app/        # Web 服务 (Flask + SocketIO)
├── core/           # 投递核心逻辑 (bot_core.py)
├── ref/            # 📌 原始参考文件 (只读，绝不动)
├── data/           # 运行时数据
├── venv/           # 虚拟环境
├── start.cmd       # 一键启动
└── .gitignore
```
