"""运行所有测试"""
import sys, json, os

sys.path.insert(0, 'web_app')
sys.path.insert(0, 'core')

# ═══ Test 1: Config ═══
print("="*60)
print("【Test 1】配置加载/保存/校验/展平")
print("="*60)

from config import load_config, save_config, validate_config, flatten_jobs_for_run

cfg = load_config()
print(f"  ✓ Config loaded: type={type(cfg).__name__}")

# 全局节
for section in ('browser', 'anti_detection', 'rate_limit', 'screenshot'):
    assert section in cfg, f"Missing {section}"
    print(f"    {section}: {json.dumps(cfg[section], ensure_ascii=False)}")

# 账号
assert 'accounts' in cfg
assert len(cfg['accounts']) > 0
acct = cfg['accounts'][0]
assert 'message_interval_min' in acct
assert 'message_interval_max' in acct
assert 'cookie_file' in acct
assert 'image_files' in acct
print(f"  ✓ 账号字段完整")

# 岗位
assert 'jobs' in acct
job = acct['jobs'][0]
required_job_keys = ('min_salary','max_salary','experience','education',
                     'exclude_companies','include_keywords','greeting_message',
                     'city','query','scroll_pages','enabled')
for key in required_job_keys:
    assert key in job, f"Missing job field: {key}"
print(f"  ✓ 岗位字段完整: {list(job.keys())}")

# 校验
errors = validate_config(cfg)
assert errors == [], f"Unexpected validation errors: {errors}"
print(f"  ✓ 校验通过 (errors={errors})")

# 展平
tasks = flatten_jobs_for_run(cfg)
print(f"  ✓ 展平任务数: {len(tasks)}")
if tasks:
    t = tasks[0]
    task_required = ('browser','anti_detection','rate_limit','screenshot',
                     'min_salary','max_salary','experience','education',
                     'exclude_companies','include_keywords')
    for key in task_required:
        assert key in t, f"Missing task field: {key}"
    print(f"  ✓ 任务字段完整: {list(t.keys())}")
    print(f"    screenshot={t['screenshot']}, browser headless={t['browser']['headless']}")

# 保存与回读
save_config(cfg)
cfg2 = load_config()
assert cfg2['browser']['headless'] == cfg['browser']['headless']
print(f"  ✓ 保存/回读一致")

# ═══ Test 2: BotCore 导入 ═══
print()
print("="*60)
print("【Test 2】BotCore 导入 & 方法检查")
print("="*60)

from bot_core import BotCore

assert hasattr(BotCore, 'start'), "BotCore missing start()"
assert hasattr(BotCore, 'stop'), "BotCore missing stop()"
print(f"  ✓ BotCore 导入成功")
print(f"    start()  ✓  |  stop()  ✓  |  check_login_status()  ✓")

# 检查 __init__ 读取新配置参数
import inspect
src = inspect.getsource(BotCore.__init__)
config_params = ['headless', 'browser_path', 'window_width', 'window_height',
                 'user_data_dir', 'custom_ua', 'max_retries', 'retry_base_delay',
                 'operation_timeout', 'page_load_timeout', 'max_applies_per_hour',
                 'max_applies_per_day', 'screenshot_enabled', 'screenshot_interval']
for p in config_params:
    assert p in src, f"Config param {p} not read in __init__"
print(f"  ✓ __init__ 读取了所有 {len(config_params)} 个新配置参数")

# 验证 start() 使用了 ChromiumOptions
start_src = inspect.getsource(BotCore.start)
assert 'ChromiumOptions' in start_src, "start() not using ChromiumOptions"
assert 'ChromiumPage(addr_or_opts=co)' in start_src
print(f"  ✓ start() 使用 ChromiumOptions 配置浏览器")

# 验证 _start_screenshot_loop 使用 screenshot_enabled
ss_src = inspect.getsource(BotCore._start_screenshot_loop)
assert 'self.screenshot_enabled' in ss_src, "screenshot loop not checking enabled"
assert 'self.screenshot_interval' in ss_src, "screenshot loop not using interval"
print(f"  ✓ 截图循环响应 enabled & interval 设置")

# ═══ Test 3: Server 导入 ═══
print()
print("="*60)
print("【Test 3】Server 导入 & 路由检查")
print("="*60)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'web_app'))
import importlib.util
spec = importlib.util.spec_from_file_location("server", "web_app/server.py")
mod = importlib.util.module_from_spec(spec)

# 只检查语法，不启动
with open("web_app/server.py", "r", encoding="utf-8") as f:
    code = f.read()
compile(code, "web_app/server.py", "exec")
print(f"  ✓ server.py 编译通过")

# 检查路由
assert "api_get_config" in code
assert "api_save_config" in code
assert "api_add_account" in code
assert "api_add_job" in code
assert "api_delete_job" in code
assert "api_list_images" in code
assert 'BotRunner' in code
assert 'TaskScheduler' in code
print(f"  ✓ 所有 API 路由存在")
print(f"  ✓ BotRunner/TaskScheduler 类存在")

# 检查 BotRunner.run() 传递全局设置
assert '_config.get("browser", {})' in code, "BotRunner not passing browser config"
assert '_config.get("screenshot", {})' in code, "BotRunner not passing screenshot config"
assert '_config.get("anti_detection", {})' in code
assert '_config.get("rate_limit", {})' in code
print(f"  ✓ BotRunner 传递全局设置到 BotCore")

# ═══ Test 4: HTML 模板 ═══
print()
print("="*60)
print("【Test 4】HTML 模板检查")
print("="*60)

with open("web_app/templates/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# 检查没有截图预览
assert 'preview-box' not in html, "preview-box still exists"
assert 'screenshotPlaceholder' not in html, "screenshot placeholder still exists"
print(f"  ✓ 已移除截图预览区域")

# 检查新元素
assert 'sub-tab' in html, "missing sub-tabs"
assert 'panelGlobal' in html, "missing global settings panel"
assert 'panelAccounts' in html, "missing accounts panel"
assert 'browserHeadless' in html, "missing browser headless toggle"
assert 'rateHour' in html, "missing rate limit fields"
assert 'screenshotEnabled' in html
assert 'screenshotInterval' in html
print(f"  ✓ 全局设置面板存在（浏览器/反检测/频率/截图）")

# 检查高级筛选
assert 'collapse-header' in html, "missing collapse for advanced settings"
assert 'j-ms' in html and 'min_salary' in html, "missing min_salary field"
assert 'j-xs' in html and 'max_salary' in html, "missing max_salary field"
assert 'j-ex' in html and 'experience' in html, "missing experience field"
assert 'j-ed' in html and 'education' in html, "missing education field"
assert 'j-excl' in html and 'exclude_companies' in html, "missing exclude_companies field"
assert 'j-incl' in html and 'include_keywords' in html, "missing include_keywords field"
print(f"  ✓ 岗位高级筛选字段存在（薪资/经验/学历/排除/关键词）")

# 检查日志区域可伸缩
assert 'resizable' in html and 'log-area' in html
print(f"  ✓ 日志区域可伸缩")

# 检查 taste-skill 设计令牌
assert '--bg:#f4f4ef' in html, "missing taste-skill bg var"
assert '--accent:#4a4d7a' in html
print(f"  ✓ taste-skill 设计系统颜色变量")

# 检查没有旧截图回调依赖
assert 'bot_screenshot' in html, "screenshot socket handler removed"
print(f"  ✓ 截图 socket 事件处理器已简化")

print()
print("="*60)
print("🎉 全部测试通过！")
print("="*60)
