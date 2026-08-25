# Boss直聘自动投递

基于 DrissionPage 的 Boss直聘自动投递工具，支持多岗位多账号、AI智能匹配、Web可视化管理。

## 功能特性

- 多岗位多账号自动投递
- AI智能匹配分析（支持多AI容灾）
- Web可视化管理界面（毛玻璃风格）
- 岗位列表管理、高级设置
- 图片作品集上传
- 投递日志记录

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

### 2. 启动

```bash
# 方式一：双击启动.bat
# 方式二：命令行
venv\Scripts\python run.py
```

访问 http://127.0.0.1:5000

## 项目结构

```
boss-auto-apply/
├── app/                          # Flask 应用主包
│   ├── server.py                 # 路由 + SocketIO
│   ├── config.py                 # 配置管理
│   ├── bot_core.py               # 自动投递核心逻辑
│   ├── ai_analyzer.py            # AI 岗位匹配分析
│   ├── templates/index.html      # Web 界面
│   ├── static/                   # 静态资源
│   └── data/                     # 运行时数据（已 gitignore）
├── venv/                         # 虚拟环境
├── requirements.txt              # Python 依赖
├── run.py                        # 入口脚本
└── 启动.bat                       # 一键启动
```

## 配置说明

首次启动后在 Web 界面配置：
- Boss直聘 Cookie
- AI API Key
- 岗位关键词、薪资范围等筛选条件
