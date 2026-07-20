"""抓取 city.json 看看完整结构"""
import json, time, sys, os
from DrissionPage import ChromiumPage

dp = ChromiumPage()
dp.get("https://www.zhipin.com")

# 不卡在登录，直接监听 city.json
print("start listen...")
dp.listen.start("data/city.json")
dp.refresh()
print("refreshed, waiting 5s...")
time.sleep(5)

for packet in dp.listen.steps():
    data = packet.response.body
    out = {"zpData_keys": list(data.get("zpData", {}).keys())}
    zp = data.get("zpData", {})
    for k, v in zp.items():
        if isinstance(v, list):
            out[f"zpData.{k}_len"] = len(v)
            if v and isinstance(v[0], dict):
                out[f"zpData.{k}_sample_keys"] = list(v[0].keys())
        elif isinstance(v, dict):
            out[f"zpData.{k}_keys"] = list(v.keys())
        else:
            out[f"zpData.{k}"] = str(v)[:100]
    
    with open("city_debug.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(json.dumps(out, ensure_ascii=False, indent=2))
    break

dp.quit()
print("done")
