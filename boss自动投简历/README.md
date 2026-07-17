# Boss 直聘 · 自动投递简历工具

基于 Python + DrissionPage 的 Boss 直聘自动化投递桌面应用，提供可视化 GUI 界面，支持城市选择、关键词搜索、自定义打招呼语、作品集图片附件上传等功能。

## 功能特性

- **可视化 GUI** — macOS/iOS 风格界面，左侧配置面板 + 右侧浏览器实时预览
- **自动登录检测** — 打开浏览器后自动检测登录状态，需手动登录后确认
- **智能搜索** — 按城市和岗位关键词搜索职位，支持滚动加载更多结果
- **自动投递** — 逐条打开职位页，发送预设打招呼语，上传作品集图片
- **去重机制** — 记录已沟通的公司，避免重复投递
- **实时截图预览** — 后台定时截图，在 GUI 中实时显示浏览器操作画面
- **运行日志** — 彩色日志输出，清晰展示每一步操作状态
- **配置持久化** — JSON 配置文件，支持保存/重置

## 环境要求

- Python 3.9+
- Windows / macOS / Linux
- Chromium 浏览器（DrissionPage 会自动管理）

## 安装

```bash
# 克隆仓库
git clone https://github.com/huangwei-gem/auto_boss.git
cd auto_boss

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

```bash
# 启动应用
python main.py
```

启动后按以下步骤操作：

1. 点击 **「开始投递」**，程序会打开 Boss 直聘首页
2. 在弹出的浏览器窗口中完成登录
3. 返回 GUI 点击 **「确认已登录」**
4. 程序将自动执行搜索 → 投递流程

## 配置说明

所有配置项位于 `bot_config.json`：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `city` | 目标城市 | 上海 |
| `job_query` | 岗位关键词 | 数据分析 |
| `scroll_pages` | 滚动加载更多次数 | 5 |
| `message_interval_min` | 消息发送最小间隔(秒) | 3 |
| `message_interval_max` | 消息发送最大间隔(秒) | 8 |
| `greeting_message` | 打招呼语 | 预设为模板文案 |
| `image_files` | 附件图片路径列表 | 数据分析看板图片 |

GUI 界面中可直接修改上述配置，点击 **「保存配置」** 即可生效。

## 项目结构

```
├── main.py          # 主入口 + GUI 界面
├── bot_core.py      # 自动投递核心逻辑
├── config.py        # 配置加载/保存/重置
├── bot_config.json  # 运行时配置
├── requirements.txt # 依赖列表
└── 数据分析看板/     # 作品集图片附件
    ├── 看板1.png
    ├── 看板2.png
    └── 看板3.png
```

## 技术栈

- **GUI**: customtkinter
- **浏览器自动化**: DrissionPage
- **图像处理**: Pillow
- **配置**: JSON

## 注意事项

- 本工具仅供个人学习使用，请勿用于商业或恶意用途
- 频繁操作可能触发平台风控，建议合理设置发送间隔
- Boss 直聘页面结构可能变化，如遇元素定位失败请提 Issue

## License

MIT
