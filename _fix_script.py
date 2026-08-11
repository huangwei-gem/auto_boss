import os

html_path = r'C:\Users\35796\Documents\coding\boss-auto-apply\web_app\templates\index.html'

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the light theme CSS - missing variable definitions
old_light_css = """[data-theme="light"], :root{

[data-theme="dark"]{"""

new_light_css = """[data-theme="light"], :root{
  --bg:#f5f6fa;--surface:#ffffff;--surface-soft:#f0f1f5;--surface-hover:#e8e9ee;
  --accent:#4a7cff;--accent-light:#e8eeff;--accent-hover:#3a6ae8;
  --success:#10b981;--success-bg:#d1fae5;--warning:#f59e0b;--warning-bg:#fef3c7;
  --danger:#ef4444;--danger-bg:#fee2e2;--info:#3b82f6;--info-bg:#dbeafe;
  --fg:#1e1e2e;--fg-2nd:#5a5d6e;--fg-3rd:#8b8fa0;--fg-4th:#b0b4c4;
  --bd:#e2e4ea;--bd-2:#d0d2da;
  --sh-sm:0 1px 2px rgba(0,0,0,.04);--sh:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --sh-md:0 4px 16px rgba(0,0,0,.08);--sh-lg:0 8px 32px rgba(0,0,0,.12);
  --side-bg:linear-gradient(180deg,#f5f6fa,#ffffff);
  --side-text:#1e1e2e;--side-input-bg:rgba(0,0,0,.03);--side-input-bd:rgba(0,0,0,.06);
  --side-label:rgba(0,0,0,.25);
  --chip-bg:#e8eeff;--chip-text:#4a7cff;--chip-del:rgba(74,124,255,.3);
  --modal-overlay:rgba(0,0,0,.3);--scrollbar-thumb:#d0d2da;
  --img-checked-bd:#4a7cff;--img-checked-bg:rgba(74,124,255,.08);
}

[data-theme="dark"]{"""

if old_light_css in content:
    content = content.replace(old_light_css, new_light_css)
    print("Fixed light theme CSS")
else:
    print("WARNING: Could not find light theme CSS")
    idx = content.find('[data-theme="light"]')
    if idx >= 0:
        print(f"Found at position {idx}")
        print(content[idx:idx+200])

# Now let's also fix the toggleTheme function to properly switch between themes
old_toggle_theme = """function toggleTheme(){
  const html=document.documentElement;
  const cur=html.getAttribute('data-theme');
  const next=cur==='dark'?'light':'dark';
  html.setAttribute('data-theme',next);
  localStorage.setItem('boss-theme',next);
  const icon=document.getElementById('themeIcon');
  if(icon) icon.innerHTML=next==='dark'?'<svg...moon>':'<svg...sun>';
}"""

# Find the actual toggleTheme function
idx = content.find("function toggleTheme")
if idx >= 0:
    end = content.find("function", idx + 20)
    if end < 0:
        end = idx + 500
    print("\n\n=== Current toggleTheme ===")
    print(content[idx:end])

# Find the loadTheme function
idx = content.find("function loadTheme")
if idx >= 0:
    end = content.find("function", idx + 20)
    if end < 0:
        end = idx + 500
    print("\n\n=== Current loadTheme ===")
    print(content[idx:end])

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
