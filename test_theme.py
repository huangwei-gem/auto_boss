import urllib.request, json, os, time

# Click the start button
body = json.dumps({"action": "click", "args": {"selector": "#btnStartAll"}, "session": "boss-test-1"}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:10086/command", data=body, headers={"Content-Type": "application/json"})
r = urllib.request.urlopen(req, timeout=10)
result = json.loads(r.read().decode("utf-8"))
with open(os.path.join("C:\\Users\\35796\\Documents\\coding\\boss-auto-apply\\test_result.txt"), "w", encoding="utf-8") as f:
    f.write("Click start: " + json.dumps(result, ensure_ascii=False, indent=2))

time.sleep(3)

# Check the log area for any output
body2 = json.dumps({"action": "evaluate", "args": {"code": "(() => { const log = document.getElementById('logArea'); const entries = log ? Array.from(log.querySelectorAll('.log-entry')).slice(-10).map(e => e.textContent.trim()).join('\\n') : 'no log area'; return JSON.stringify(entries.slice(0, 2000)); })()"}, "session": "boss-test-1"}).encode("utf-8")
req2 = urllib.request.Request("http://127.0.0.1:10086/command", data=body2, headers={"Content-Type": "application/json"})
r2 = urllib.request.urlopen(req2, timeout=10)
result2 = json.loads(r2.read().decode("utf-8"))
with open(os.path.join("C:\\Users\\35796\\Documents\\coding\\boss-auto-apply\\test_result2.txt"), "w", encoding="utf-8") as f:
    f.write("Log: " + json.dumps(result2, ensure_ascii=False, indent=2))

print("Done")
