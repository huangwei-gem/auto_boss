"""API 集成测试"""
import urllib.request, json, sys

BASE = "http://127.0.0.1:5000"

def ok(name, msg=""):
    print(f"  ✓ {name}" + (f"  ({msg})" if msg else ""))

def fail(name, err):
    print(f"  ✗ {name}: {err}")
    return False

all_pass = True

# ── 1. 首页 ──
try:
    r = urllib.request.urlopen(f"{BASE}/")
    html = r.read().decode()
    assert "f4f4ef" in html, "CSS vars not found"
    assert "panelGlobal" in html, "global panel missing"
    assert "browserHeadless" in html, "headless toggle missing"
    assert "taste-skill" in html
    ok("首页 HTML 加载", f"{len(html)} bytes, taste-skill 风格")
except Exception as e:
    all_pass = False
    fail("首页", e)

# ── 2. GET 配置 ──
try:
    r = urllib.request.urlopen(f"{BASE}/api/config")
    cfg = json.loads(r.read())
    assert "browser" in cfg
    assert "screenshot" in cfg
    assert "anti_detection" in cfg
    assert "rate_limit" in cfg
    assert "accounts" in cfg
    ok("GET /api/config", f"全局节: {list(cfg.keys())}")
except Exception as e:
    all_pass = False
    fail("GET /api/config", e)

# ── 3. PUT 配置（保存全局设置）──
try:
    cfg["browser"]["headless"] = True
    cfg["browser"]["window_width"] = 1920
    cfg["screenshot"]["enabled"] = False
    cfg["screenshot"]["interval"] = 5.0
    cfg["anti_detection"]["max_retries"] = 5
    cfg["rate_limit"]["max_applies_per_hour"] = 20

    data = json.dumps(cfg).encode()
    req = urllib.request.Request(f"{BASE}/api/config", data=data,
                                  headers={"Content-Type":"application/json"}, method="PUT")
    r = urllib.request.urlopen(req)
    res = json.loads(r.read())
    assert res["status"] == "ok", f"status={res['status']}"

    # 回读
    r = urllib.request.urlopen(f"{BASE}/api/config")
    cfg2 = json.loads(r.read())
    assert cfg2["browser"]["headless"] == True
    assert cfg2["browser"]["window_width"] == 1920
    assert cfg2["screenshot"]["enabled"] == False
    assert cfg2["screenshot"]["interval"] == 5.0
    assert cfg2["anti_detection"]["max_retries"] == 5
    assert cfg2["rate_limit"]["max_applies_per_hour"] == 20
    ok("PUT /api/config 全局设置保存并回读")
except Exception as e:
    all_pass = False
    fail("PUT /api/config", e)

# ── 4. 还原配置 ──
try:
    cfg["browser"]["headless"] = False
    cfg["browser"]["window_width"] = 1280
    cfg["screenshot"]["enabled"] = True
    cfg["screenshot"]["interval"] = 3.0
    cfg["anti_detection"]["max_retries"] = 3
    cfg["rate_limit"]["max_applies_per_hour"] = 30
    data = json.dumps(cfg).encode()
    req = urllib.request.Request(f"{BASE}/api/config", data=data,
                                  headers={"Content-Type":"application/json"}, method="PUT")
    urllib.request.urlopen(req)
    ok("配置已还原")
except Exception as e:
    all_pass = False
    fail("还原配置", e)

# ── 5. 添加账号 ──
try:
    req = urllib.request.Request(f"{BASE}/api/config/accounts", method="POST")
    r = urllib.request.urlopen(req)
    res = json.loads(r.read())
    assert res["status"] == "ok"
    ok("POST 添加账号", f"共 {len(res['accounts'])} 个账号")
except Exception as e:
    all_pass = False
    fail("添加账号", e)

# ── 6. 添加岗位（含高级字段）──
try:
    req = urllib.request.Request(f"{BASE}/api/config/accounts/0/jobs", method="POST")
    r = urllib.request.urlopen(req)
    res = json.loads(r.read())
    assert res["status"] == "ok"

    # 验证新岗位字段
    cfg = json.loads(urllib.request.urlopen(f"{BASE}/api/config").read())
    job = cfg["accounts"][0]["jobs"][-1]
    for field in ("min_salary","max_salary","experience","education","exclude_companies","include_keywords"):
        assert field in job, f"Missing {field}"
    ok("POST 添加岗位", f"新岗位字段: {list(job.keys())}")
except Exception as e:
    all_pass = False
    fail("添加岗位", e)

# ── 7. 删除岗位 ──
try:
    cfg = json.loads(urllib.request.urlopen(f"{BASE}/api/config").read())
    last_idx = len(cfg["accounts"][0]["jobs"]) - 1
    req = urllib.request.Request(f"{BASE}/api/config/accounts/0/jobs/{last_idx}", method="DELETE")
    r = urllib.request.urlopen(req)
    res = json.loads(r.read())
    assert res["status"] == "ok"
    ok("DELETE 删除岗位")
except Exception as e:
    all_pass = False
    fail("删除岗位", e)

# ── 8. 删除账号 ──
try:
    cfg = json.loads(urllib.request.urlopen(f"{BASE}/api/config").read())
    last_idx = len(cfg["accounts"]) - 1
    req = urllib.request.Request(f"{BASE}/api/config/accounts/{last_idx}", method="DELETE")
    r = urllib.request.urlopen(req)
    res = json.loads(r.read())
    assert res["status"] == "ok"
    ok("DELETE 删除账号")
except Exception as e:
    all_pass = False
    fail("删除账号", e)

# ── 9. 图片列表 ──
try:
    r = urllib.request.urlopen(f"{BASE}/api/images")
    imgs = json.loads(r.read())
    assert isinstance(imgs, list)
    ok("GET /api/images", f"{len(imgs)} 张图片")
except Exception as e:
    all_pass = False
    fail("图片列表", e)

# ── 10. 状态 ──
try:
    r = urllib.request.urlopen(f"{BASE}/api/status")
    s = json.loads(r.read())
    assert "running" in s
    ok("GET /api/status")
except Exception as e:
    all_pass = False
    fail("状态", e)

print()
if all_pass:
    print("🎉 全部 API 测试通过！（10/10）")
else:
    print(f"⚠️  部分测试失败")
    sys.exit(1)
