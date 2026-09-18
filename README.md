# Boss直聘自动投递

基于 DrissionPage 的 Boss直聘自动投递工具，支持多岗位多账号、AI智能匹配、Web可视化管理。

## 功能特性

- 多岗位多账号自动投递
- AI智能匹配分析（支持多AI容灾：Agnes + SenseNova GLM-5.2 + DeepSeek）
- 多浏览器支持（便携浏览器/Chrome/Edge，自动检测）
- 结构化日志系统（分类查询、错误摘要）
- Web可视化管理界面（毛玻璃风格）
- 岗位列表管理、高级设置
- 图片作品集上传
- 投递日志记录

## 快速开始

### 支持平台

| 平台 | 状态 | 启动方式 |
|------|------|----------|
| Windows 10/11 | ✅ 支持 | 双击 `启动.bat` |
| macOS 12+ (Intel/Apple Silicon) | ✅ 支持 | `./start.sh` |
| Linux (Ubuntu/Debian) | ✅ 支持 | `./start.sh` |

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
chmod +x start.sh
./start.sh
```

访问 http://127.0.0.1:5000

### 3. 首次配置

1. 浏览器访问 http://127.0.0.1:5000
2. 在 Web 界面中配置：
   - **Boss直聘 Cookie**：登录 Boss直聘后，在浏览器开发者工具中复制 Cookie 上传
   - **AI API Key**：填入你的 Agnes 或其他兼容 API Key
   - **岗位配置**：设置搜索关键词、城市、打招呼语等
   - **简历信息**：填写学校、专业、技能等（用于 AI 匹配分析）

## 项目结构

```
auto_boss/
├── app/                          # Flask 应用主包
│   ├── server.py                 # 路由 + SocketIO
│   ├── config.py                 # 配置管理
│   ├── bot_core.py               # 自动投递核心逻辑
│   ├── ai_analyzer.py            # AI 岗位匹配分析（单接口）
│   ├── ai_analyzer_chain.py      # AI 容灾链（多接口自动切换）
│   ├── browser_launcher.py       # 多浏览器启动器
│   ├── logging_system.py         # 结构化日志系统
│   ├── templates/index.html      # Web 界面
│   ├── static/                   # 静态资源
│   └── data/                     # 运行时数据
│       ├── logs/                 # 日志文件
│       └── bot_config.json       # 配置（自动生成）
├── cloakbrowser-windows-x64/     # 便携浏览器（可选）
├── venv/                         # 虚拟环境
├── requirements.txt              # Python 依赖
├── run.py                        # 入口脚本
└── 启动.bat                       # 一键启动
```

## AI 多接口容灾

系统支持多个 AI 接口，按优先级自动切换：

| 优先级 | 名称 | 模型 | 接口地址 |
|--------|------|------|----------|
| 1 | Agnes-2.5-Flash | agnes-2.5-flash | https://apihub.agnes-ai.com/v1 |
| 2 | SenseNova-GLM-5.2 | glm-5.2 | https://token.sensenova.cn/v1 |
| 3 | SenseNova-DeepSeek | deepseek-v4-flash | https://token.sensenova.cn/v1 |

当主接口失败时，自动切换到下一个接口。

## 多浏览器支持

Windows 下自动检测以下浏览器，按优先级使用：

1. **便携浏览器**（`cloakbrowser-windows-x64/chrome.exe`）— 无需安装，开箱即用
2. **Google Chrome** — 系统安装版本
3. **Microsoft Edge** — 系统安装版本

可通过 Web API 切换偏好浏览器：

```bash
# 查看可用浏览器
curl http://127.0.0.1:5000/api/browser/list

# 设置偏好浏览器
curl -X POST http://127.0.0.1:5000/api/browser/set \
  -H "Content-Type: application/json" \
  -d '{"browser":"portable"}'
```

## 日志查询 API

```bash
# 查看所有日志
curl "http://127.0.0.1:5000/api/logs?limit=50"

# 只看错误
curl "http://127.0.0.1:5000/api/logs/errors?hours=24"

# 按类别查询（BOT/AI/BROWSER/SCHEDULER）
curl "http://127.0.0.1:5000/api/logs?category=AI&limit=20"

# 关键词搜索
curl "http://127.0.0.1:5000/api/logs?search=匹配度"
```

## 配置说明

首次启动后在 Web 界面配置（参考 `app/data/bot_config.example.json`）：
- Boss直聘 Cookie（登录后从浏览器复制）
- AI API Key（Agnes 或其他兼容 OpenAI 格式的 API）
- 岗位关键词、薪资范围等筛选条件
- 简历信息（学校、专业、技能等）

## 跨平台支持

- **Windows**：双击 `启动.bat` 即可
- **Mac/Linux**：终端运行 `./start.sh`

### 系统要求

- **Python**：3.8 或更高版本
- **Chrome**：Google Chrome 90+ 或便携浏览器
- **内存**：至少 4GB 可用内存
- **网络**：能正常访问 Boss直聘

### macOS 特别说明

macOS 上使用独立的浏览器启动器（`browser_launcher.py`），解决了 DrissionPage 在 macOS 上的 WebSocket 连接兼容性问题。首次启动时会自动：
1. 检测 Chrome 安装位置
2. 启动 Chrome 并开启远程调试
3. 通过 CDP 协议连接浏览器

如果遇到 "Chrome not found" 错误，请确保已安装 Google Chrome。
