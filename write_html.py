import os
import sys
d = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(d, "web_app", "templates", "index.html")
with open(p, "r", encoding="utf-8") as f:
    old = f.read()
print(f"Old size: {len(old)}")
