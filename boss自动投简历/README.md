# Boss 直聘 · 自动投递简历工具

基于 Python + DrissionPage 的 Boss 直聘自动化投递桌面应用。  
**多账号 · 多岗位 · Cookie 连通性测试 · 实时浏览器预览**

## 功能特性

- **多账号管理** — 添加/删除/切换多个 Boss 直聘账号，每个账号独立配置
- **多岗位投递** — 每个账号可配置多个岗位关键词，批量搜索投递
- **智能解析** — 自动解析薪资、经验、学历、公司规模、招聘者活跃度
- **自动去重** — 记录已沟通公司，避免重复投递
- **作品集上传** — 支持发送招呼语后自动上传图片附件
- **实时预览** — 浏览器截图实时显示在 GUI 中
- **彩色日志** — 清晰的日志输出，实时了解投递进度
- **连通性测试** — 一键测试登录状态、城市码、岗位获取是否正常
- **配置持久化** — JSON 配置文件，可视化编辑，支持保存/重置

## 环境要求

- Python 3.9+
- Windows / macOS / Linux
- Chromium 浏览器（DrissionPage 会自动管理）

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/huangwei-gem/auto_boss.git
cd auto_boss

# 创建虚拟环境
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动应用
python main.py
```

## 使用指南

1. **添加账号** — 左侧点击「+ 添加账号」，输入城市、岗位关键词
2. **配置招呼语** — 在配置面板中可以自定义每账号的打招呼消息
3. **添加图片** — 可选上传作品集截图（数据分析看板等）
4. **点击「开始投递」** — 程序打开 Boss 直聘首页
5. **手动登录** — 在打开的浏览器中完成登录
6. **点击「确认已登录」** — 程序自动搜索 → 投递
7. **随时「停止」** — 安全中断运行

## 项目结构

```
├── main.py              # 主入口 + 现代化 GUI 界面
├── bot_core.py          # 自动投递核心（对齐 mian.py 全部逻辑）
├── config.py            # 配置加载/保存/迁移（自动兼容旧版）
├── bot_config.json      # 运行时配置
├── requirements.txt     # 依赖列表
├── chats_log/           # 沟通记录（自动生成）
├── .venv/               # 虚拟环境
└── 数据分析看板/         # 示例作品集图片
    ├── 看板1.png
    ├── 看板2.png
    └── 看板3.png
```

## 配置说明

配置文件 `bot_config.json` 格式：

| 字段 | 说明 |
|------|------|
| `accounts[].name` | 账号名称 |
| `accounts[].city` | 目标城市 |
| `accounts[].jobs[].query` | 岗位关键词 |
| `accounts[].jobs[].scroll_pages` | 滚动加载次数 |
| `accounts[].greeting_message` | 打招呼语 |
| `accounts[].image_files` | 图片附件路径 |
| `message_interval_min/max` | 投递间隔（秒） |

## 技术栈

- **GUI**: customtkinter（现代化暗/亮主题）
- **浏览器自动化**: DrissionPage
- **图像处理**: Pillow
- **配置**: JSON

## 注意事项

- 本工具仅供个人学习使用
- 请合理设置投递间隔，避免触发平台风控
- 建议使用虚拟环境运行，避免依赖冲突

## License

MIT
