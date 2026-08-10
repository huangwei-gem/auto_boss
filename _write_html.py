
import os
html_path = r'C:\Users\35796\Documents\coding\boss-auto-apply\web_app\templates\index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    old = f.read()
print(f'Old size: {len(old)}')
