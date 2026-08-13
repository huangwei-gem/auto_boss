# 数据抓取缺口清单（Boss直聘自动投递）— 校准结果

> 生成时间：2026-08-12
> 更新：2026-08-13 — 已用真实 DOM 完成全部核心选择器校准（cloakbrowser 抓取 + verify_parse 真实验证）

## 校准结论

绝大部分缺口已通过真实 DOM 解决。**薪资 iconfont 乱码**是额外发现并已解决（Boss 用私用区字体映射数字，解码规则 `cp - 0xE031 = 数字`，实测通过）。

## 缺口表（状态）

| # | 数据点 | 最终选择器/方法 | 状态 |
|---|---|---|---|
| 1 | 岗位卡片：名称/薪资/经验/学历/公司+地点 | `.job-card-box` 卡片内 `.job-name` / `.job-salary` / `.tag-list`(按行拆) / `.boss-name` / `.company-location` | ✅ 已解决（verify_parse 15 卡验证通过） |
| 2 | 岗位名称链接（列表页） | `.job-name` 的 `href` | ✅ 已解决 |
| 3 | 岗位详情页薪资 | `.salary` + iconfont 解码 | ✅ 已解决 |
| 4 | 岗位描述 | `.job-sec-text` | ✅ 已解决（详情页抓取成功） |
| 5 | 公司规模 | `.icon-scale` | ✅ 已解决 |
| 6 | HR 上线状态 | `.boss-online-tag` | ✅ 已解决 |
| 7 | 沟通按钮（已沟通判断） | `.btn-startchat`；**已沟通=文本「继续沟通」+`data-isfriend="true"`**；未沟通=「立即沟通」+`isfriend="false"` | ✅ 已解决（实测 4 岗位验证） |
| 8 | 消息输入框（投递时） | `.input-area`（详情页沟通弹窗 textarea，placeholder「请简短描述您的问题」） | ✅ 已解决（实测点击沟通后 DOM） |
| 9 | 发送按钮（投递时） | `.send-message` | ✅ 已解决（实测点击沟通后 DOM） |
| 10 | 关闭弹层按钮 | `.ui-icon-close` | ✅ 已解决 |
| 11 | 作品图片上传 | `tag:input@@type=file` | ✅ 稳定 |
| 12 | 会话页消息气泡 | `li.message-item.item-friend .text-content`（仅 HR 消息） | ✅ 已解决 |
| 13 | 会话列表行 | `.friend-content-warp`（li 内） | ✅ 已解决 |
| 14 | 会话岗位名/公司 | 岗位名 `.position-name`；公司 `.friend-content .name-box span:nth-child(2)` | ✅ 已解决 |
| 15 | 会话页输入框/发送按钮 | `#chat-input`（contenteditable） / `.btn-send` | ✅ 已解决（会话页专用，与投递弹窗 `.input-area`/`.send-message` 不同） |
| 16 | 聊天接口嗅探（层A） | `CHAT_API_KEYWORDS` | ⏳ 待值守实机观察确认（DOM 层 B 可用兜底） |

## 实测校准补充（2026-08-13 真实投递验证）

- **沟通按钮判断（关键纠错）**：页面主体按钮 `ka` **恒为** `go_chat_done_xxx`，已沟通与未沟通一致，**不能作为依据**。唯一可靠区分：未沟通=文本「立即沟通」+`data-isfriend="false"`；已沟通=文本「继续沟通」+`data-isfriend="true"`。已按此修正 `_apply_job`。
- **两个输入场景选择器不同**：投递时点「立即沟通」在详情页弹窗内输入（`.input-area` textarea + `.send-message` 按钮）；值守回复在会话页输入（`#chat-input` contenteditable + `.btn-send`）。已分别校准。
- **薪资 iconfont**：详情页/列表页薪资均需解码（`cp - 0xE031 = 数字`），已统一处理。
- **实投验证结果**：对未沟通岗位完整走通「点立即沟通 → `.input-area` 输入 → `.send-message` 发送」，随后回访确认按钮变「继续沟通」+`isfriend="true"`，消息真实送达。

## 风控 / 滑块（已实现）

- `bot_core.py` 新增 `human_verify` 配置段（`enabled` / `wait_timeout`，默认开 / 180s）。
- `HUMAN_VERIFY_JS` 特征探测：`#Tcaptcha-frame`/`#tcaptcha_iframe`、`iframe[src*='captcha'|'tcaptcha'|'verify']`、`[class*='captcha'|'tcaptcha'|'slider']`、`[id*='captcha']`、`[class*='verify-block'|'verify-code']`。
- 命中 → 暂停投递/值守 → 日志提示用户在浏览器手动完成 → 每 2~4s 轮询直到弹层消失 → 继续；超时则放弃当前操作（点击/发送后超时会标记已处理避免重复触发）。
- 插入点：投递的详情页加载后、点击「立即沟通」后、发送消息后、发送图片后；值守发送回复后。
- ⏳ 待实机确认：滑块弹层真实 DOM 是否命中探测特征（若 Boss 弹层 class 与特征不符，抓一次弹层 HTML 补特征即可）。

## 待办（非选择器）

1. **简历 profile**：Web UI → AI 智能解析 → 编辑简历，填学校/专业/学历/技能/经验/求职意向。
2. **有效登录态**：已由 cloakbrowser `~/.zhipin_dp_data` 登录态维持（verify_parse 直接以已登录状态运行）。
3. **真实投递会打扰 HR**：投递 = 真实发打招呼。建议先用 1 个岗位小规模验证再全量。
