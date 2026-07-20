# UI_OVERHAUL — 修复启动/布局优化/设置全面化

## 问题清单
1. ❌ `BotCore` 没有 `start` 属性（缓存/编译问题，已清 pycache）
2. ❌ 浏览器没真正启动（ChromiumPage 需配置 headed 模式）
3. ❌ 不要截图预览窗口
4. ❌ 布局不够好（参考 taste-skill）
5. ❌ 设置只能调部分参数，需要全部暴露

## 步骤

### Step 1: 验证 BotCore 导入 && 修复缓存问题
- [x] 清除所有 __pycache__
- [x] 验证 Python 能正常导入 BotCore 并调用 start()

### Step 2: 扩展配置 schema (config.py)
- [x] 新增浏览器配置: browser_path, window_width, window_height, headless, user_data_dir
- [x] 新增反检测配置: user_agent (可选列表/自定义)
- [x] 新增重试配置: max_retries, retry_base_delay
- [x] 新增频率限制配置: max_applies_per_hour, max_applies_per_day
- [x] 新增延时配置: page_load_timeout, operation_timeout
- [x] 新增截图配置: screenshot_enabled (控制是否传截图到前端)
- [x] 更新 validate_config() 和 flatten_jobs_for_run()
- [x] 更新 DEFAULT_CONFIG

### Step 3: 更新 BotCore (bot_core.py)
- [x] 从 config 读取所有新参数
- [x] 浏览器启动时使用 config 中的路径/窗口/headless 设置
- [x] 使用 config 中的重试/限速/延时设置
- [x] 根据 screenshot_enabled 决定是否调用截图回调

### Step 4: 重写前端界面 (index.html)
- [x] **移除截图预览区域** — 替换为实时状态卡片+日志
- [x] **右面板重构**: 上半部实时状态+统计卡片，下半部日志（可伸缩）
- [x] **左面板优化**:
  - [x] 每个岗位卡片增加"高级设置"折叠面板（薪资、经验、学历等）
  - [x] 全局设置标签页（浏览器、反检测、频率限制、截图设置）
  - [x] 更好的分组和布局
- [x] **taste-skill 风格优化**: 卡片化、间距调整、颜色微调

### Step 5: 更新后端 API (server.py)
- [x] 更新 API 路由以支持新的嵌套配置字段
- [x] 确保所有新字段在 config 的 save/load 中正确序列化
- [x] BotRunner 传递全局设置到 BotCore

### Step 6: 验证
- [x] 配置加载/保存测试通过
- [x] BotCore 导入并验证新参数读取
- [x] Python 代码语法检查通过
