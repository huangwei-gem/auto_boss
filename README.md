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
# Windows
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动

```bash
# Windows：双击 启动.bat，或命令行
venv\Scripts\python run.py

# Mac/Linux
source venv/bin/activate
python run.py
```

访问 http://127.0.0.1:5000

### 3. 首次配置

1. 浏览器访问 http://127.0.0.1:5000
2. 在 Web 界面中配置：
   - **Boss直聘 Cookie**：登录 Boss直聘后，在浏览器开发者工具中复制 Cookie 上传
   - **AI API Key**：填入你的 Agnes 或其他兼容 API Key
   - **岗位配置**：设置搜索关键词、城市、打招呼语等
   - **简历信息**：填写学校、专业、技能等（用于 AI 匹配分析）
3. 参考 `app/data/bot_config.example.json` 了解配置格式

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

首次启动后在 Web 界面配置（参考 `app/data/bot_config.example.json`）：
- Boss直聘 Cookie（登录后从浏览器复制）
- AI API Key（Agnes 或其他兼容 OpenAI 格式的 API）
- 岗位关键词、薪资范围等筛选条件
- 简历信息（学校、专业、技能等）

## 跨平台支持

- **Windows**：双击 `启动.bat` 即可
- **Mac/Linux**：终端运行 `source venv/bin/activate && python run.py`
