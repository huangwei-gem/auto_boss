# Boss直聘自动投递

基于 DrissionPage 的 Boss直聘自动投递工具，**自带浏览器**，无需额外安装 Chrome。支持多岗位多账号、AI智能匹配、Web可视化管理、BrowserSkill 扩展集成。

## 功能特性

- **自带浏览器**：内置 Chromium，无需安装 Chrome，解压即用
- **BrowserSkill 集成**：加载 AI 浏览器扩展，支持 AI 定制化操作
- 多岗位多账号自动投递
- AI智能匹配分析（支持多AI容灾）
- Web可视化管理界面（毛玻璃风格）
- 岗位列表管理、高级设置
- 图片作品集上传
- 投递日志记录
- **按账号分离统计**：每个账号独立显示总任务/已投递/已跳过
- **浏览器保活**：防止 Chrome 冻结/丢弃标签页
- **任务完成后浏览器保持运行**：无需重复登录

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

### 2. 下载便携浏览器（首次使用）

便携浏览器未包含在 Git 仓库中（体积约 500MB），需要单独下载：

1. 下载 `cloakbrowser-windows-x64.zip`（请联系维护者或从 Release 页面下载）
2. 解压到项目根目录，确保存在 `cloakbrowser-windows-x64/chrome.exe`
3. （可选）下载 `browser-extension` 文件夹放到项目根目录，启用 BrowserSkill 扩展

### 3. 启动

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
├── cloakbrowser-windows-x64/     # 自带 Chromium 浏览器
├── browser-skill-extension-v0.1.7-chrome/  # BrowserSkill 扩展
├── venv/                         # 虚拟环境
├── requirements.txt              # Python 依赖
├── run.py                        # 入口脚本
└── 启动.bat                       # 一键启动
```

## 投递流程

### 流程A（传统）
点击「立即沟通」→ 出现输入框 → 输入打招呼语 → 点击发送 → 发送图片

### 流程B（弹窗）
点击「立即沟通」→ Boss 自动发默认消息 → 弹窗「留在此页/继续沟通」→ 点击「继续沟通」→ 进入完整聊天窗口 → 输入自定义打招呼语 → 发送

## 配置说明

首次启动后在 Web 界面配置（参考 `app/data/bot_config.example.json`）：
- Boss直聘 Cookie（登录后从浏览器复制）
- AI API Key（Agnes 或其他兼容 OpenAI 格式的 API）
- 岗位关键词、薪资范围等筛选条件
- 简历信息（学校、专业、技能等）

## 跨平台支持

- **Windows**：双击 `启动.bat` 即可
- **Mac/Linux**：终端运行 `source venv/bin/activate && python run.py`
