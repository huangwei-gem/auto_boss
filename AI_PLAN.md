# Boss直聘 AI 智能投递助手 — 方案文档

## 一、概述

基于现有 Boss直聘自动投递项目，引入 AI 智能解析能力，实现：
1. **智能岗位匹配** — 自动分析招聘描述与用户简历的匹配度
2. **智能排序** — 按匹配度从高到低排序岗位
3. **智能打招呼** — 根据岗位要求自动生成个性化打招呼消息
4. **自动投递** — 只投递匹配度高于阈值的岗位

## 二、技术架构

### 现有架构
用户 (Web UI) → Flask Server → BotCore (DrissionPage) → Chrome 浏览器 → Boss直聘
Socket.IO (实时日志)

### 新增 AI 模块
用户 (Web UI) → Flask Server → BotCore → AI 分析模块 → Agnes API (agnes-2.5-flash)
Socket.IO (实时日志) / Job Matching Results

### AI 模块组件
1. ai_analyzer.py — 核心 AI 分析引擎，调用 Agnes API 分析岗位描述，缓存分析结果
2. resume_parser.py — 简历解析器，将用户填写的个人信息转为结构化简历
3. job_matcher.py — 岗位匹配引擎，计算岗位与简历的匹配度

## 三、AI 分析流程

### 3.1 岗位匹配流程
1. 用户填写简历信息（教育背景、技能、工作经验、求职意向）
2. 系统启动后，BotCore 获取岗位列表
3. 对每个岗位，提取岗位名称、薪资范围、岗位描述、任职要求、公司信息
4. 发送给 AI 分析模块调用 Agnes API 进行评估
5. 返回匹配评分（0-100）和原因
6. 岗位按评分排序，高于阈值的自动投递

### 3.2 Prompt 设计
System: 你是 Boss直聘智能投递助手的岗位匹配分析专家
User: 分析求职者简历与招聘岗位的匹配度，返回 JSON 格式评分和理由

## 四、配置文件变更

新增 ai 和 resume 字段到 bot_config.json
AI 字段：enabled, api_key, api_base_url, model, match_threshold
简历字段：education, skills, experience, target_position

## 五、实现步骤

Phase 1: 基础设施
- 创建 core/ai_analyzer.py
- 创建 core/resume_manager.py
- 创建 core/job_matcher.py
- 更新 config.py
- 更新 server.py

Phase 2: 前端
- 简历编辑面板
- AI 设置面板
- 匹配度展示
- 匹配详情弹窗

Phase 3: 集成
- BotCore 中添加 AI 分析步骤
- 缓存机制
- 降级处理

Phase 4: 优化
- 批量分析
- 流式输出
- 错误重试和限流

## 六、API 路由设计

GET  /api/resume              — 获取简历信息
PUT  /api/resume              — 保存简历信息
POST /api/ai/analyze          — 手动分析某个岗位
POST /api/ai/analyze-batch    — 批量分析岗位
GET  /api/ai/cache            — 查看分析缓存
POST /api/ai/cache/clear      — 清空分析缓存
GET  /api/ai/stats            — AI 分析统计

## 七、风险与应对

1. API 不可用 → 降级到原始逻辑
2. 分析速度慢 → 批量分析 + 缓存 + 异步
3. 匹配不准确 → 可调节阈值 + 手动覆盖
4. API Key 泄露 → 后端代理调用
