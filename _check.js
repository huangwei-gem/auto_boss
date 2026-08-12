
const socket = io();
let config = { accounts: [] };
let activeAccountIdx = 0;
const defaultGreeting = "您好，我是双一流的本科，应聘数据分析岗位。在校系统学习数据分析相关知识，掌握Excel、基础SQL与数据整理技能，具备数据思维。做事严谨细心，学习能力强，愿意踏实积累。十分认可贵公司，希望能获得面试机会。";
let stats = { total: 0, applied: 0, skipped: 0 };
let availableImages = [];
  refreshImageList();

function renderAiConfig() {
  if (!config.ai) config.ai = {};
  config.ai = Object.assign({enabled:false,api_key:'',api_base:'https://apihub.agnes-ai.com/v1',model:'agnes-2.5-flash',match_threshold:70}, config.ai);
  setEl('aiEnabled', 'toggle-switch' + (config.ai.enabled ? ' on' : ''));
  setVal('aiApiKey', config.ai.api_key || '');
  setVal('aiApiBase', config.ai.api_base || 'https://apihub.agnes-ai.com/v1');
  setVal('aiModel', config.ai.model || 'agnes-2.5-flash');
  setVal('aiThreshold', config.ai.match_threshold ?? 70);
  const badge = document.getElementById('aiBadge');
  if (badge) badge.textContent = config.ai.enabled ? '开' : '关';
}

function toggleAiEnabled() {
  if (!config.ai) config.ai = {};
  config.ai.enabled = !config.ai.enabled;
  renderAiConfig();
  saveConfig();
  addLog('INFO', 'AI 智能解析已' + (config.ai.enabled ? '开启' : '关闭'));
}

function onAiChange() {
  if (!config.ai) config.ai = {};
  config.ai.enabled = document.getElementById('aiEnabled').classList.contains('on');
  config.ai.api_key = document.getElementById('aiApiKey').value.trim();
  config.ai.api_base = document.getElementById('aiApiBase').value.trim() || 'https://apihub.agnes-ai.com/v1';
  config.ai.model = document.getElementById('aiModel').value.trim() || 'agnes-2.5-flash';
  config.ai.match_threshold = parseInt(document.getElementById('aiThreshold').value) || 70;
  renderAiConfig();
  saveConfig();
}

function testAi() {
  const status = document.getElementById('aiStatus');
  if (!config.ai || !config.ai.api_key) {
    if (status) status.textContent = '请先填写 API Key 并保存';
    addLog('ERROR', 'AI 测试失败: API Key 未配置');
    return;
  }
  if (status) status.textContent = '⏳ 正在测试 AI 分析...';
  onAiChange();
  saveConfig().then(function() {
    return fetch('/api/ai/config', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:config.ai.enabled, api_key:config.ai.api_key, api_base:config.ai.api_base, model:config.ai.model, match_threshold:config.ai.match_threshold})});
  }).then(r=>r.json()).then(function(data) {
    if (data.status !== 'ok') throw new Error(data.message || '保存 AI 配置失败');
    const sample = {
      job_name: '数据分析师',
      salary: '15-25K',
      description: '负责业务数据分析，输出报表与洞察，支持决策。要求掌握SQL与Excel。',
      requirements: '本科及以上，熟悉SQL、Excel，有数据思维',
      company: '示例公司',
      url: 'https://www.zhipin.com/job_detail/test.html'
    };
    return fetch('/api/ai/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job: sample})});
  }).then(r=>r.json()).then(function(data) {
    if (data.status !== 'ok') throw new Error(data.message || 'AI 分析失败');
    const r = data.result || {};
    if (status) status.textContent = '✓ AI 测试成功，匹配度: ' + (r.score ?? '?') + '/100';
    addLog('SUCCESS', 'AI 测试成功: 匹配度 ' + (r.score ?? '?') + '/100 —— ' + (r.reason || ''));
  }).catch(function(e) {
    if (status) status.textContent = '✗ 测试失败: ' + e.message;
    addLog('ERROR', 'AI 测试失败: ' + e.message);
  });
}

function showResumeModal() {
  if (!config.resume) config.resume = {};
  config.resume = Object.assign({school:'',major:'',degree:'',skills:[],experience:'',target_position:'',self_intro:''}, config.resume);
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'resumeModal';
  overlay.innerHTML =
    '<div class="modal">'+
      '<h3>📄 编辑简历（用于 AI 匹配分析）</h3>'+
      '<div class="modal-field"><label>学校</label><input id="resumeSchool" value="'+escHtml(config.resume.school||'')+'" placeholder="例如: 某某大学"></div>'+
      '<div class="modal-field"><label>专业</label><input id="resumeMajor" value="'+escHtml(config.resume.major||'')+'" placeholder="例如: 统计学"></div>'+
      '<div class="modal-field"><label>学历</label><input id="resumeDegree" value="'+escHtml(config.resume.degree||'')+'" placeholder="例如: 本科"></div>'+
      '<div class="modal-field"><label>技能（逗号分隔）</label><input id="resumeSkills" value="'+escHtml((config.resume.skills||[]).join(', '))+'" placeholder="例如: Excel, SQL, Python"></div>'+
      '<div class="modal-field"><label>工作经验</label><textarea id="resumeExperience" placeholder="简要描述工作/项目经验" style="min-height:60px">'+escHtml(config.resume.experience||'')+'</textarea></div>'+
      '<div class="modal-field"><label>求职意向</label><input id="resumeTarget" value="'+escHtml(config.resume.target_position||'')+'" placeholder="例如: 数据分析师"></div>'+
      '<div class="modal-field"><label>自我介绍</label><textarea id="resumeIntro" placeholder="自我介绍（可用于打招呼消息）" style="min-height:60px">'+escHtml(config.resume.self_intro||'')+'</textarea></div>'+
      '<div class="modal-actions">'+
        '<button class="btn btn-primary" onclick="saveResumeModal()">保存</button>'+
        '<button class="btn btn-cancel" onclick="closeResumeModal()">取消</button>'+
      '</div>'+
    '</div>';
  document.body.appendChild(overlay);
}

function closeResumeModal() {
  const m = document.getElementById('resumeModal');
  if (m) m.remove();
}

function saveResumeModal() {
  if (!config.resume) config.resume = {};
  config.resume.school = document.getElementById('resumeSchool').value.trim();
  config.resume.major = document.getElementById('resumeMajor').value.trim();
  config.resume.degree = document.getElementById('resumeDegree').value.trim();
  config.resume.skills = document.getElementById('resumeSkills').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean);
  config.resume.experience = document.getElementById('resumeExperience').value.trim();
  config.resume.target_position = document.getElementById('resumeTarget').value.trim();
  config.resume.self_intro = document.getElementById('resumeIntro').value.trim();
  closeResumeModal();
  fetch('/api/resume', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(config.resume)})
    .then(r=>r.json()).then(function(data) {
      if (data.status === 'ok') addLog('SUCCESS', '简历已保存');
      else addLog('ERROR', '保存简历失败: ' + (data.message||''));
    }).catch(e => addLog('ERROR', '保存简历失败: ' + e.message));
}

function toggleTheme() {
  const html = document.documentElement;
  const isDark = html.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('boss-theme', next);
  updateThemeUI(next);
}

function loadTheme() {
  let saved = localStorage.getItem('boss-theme');
  if (!saved) {
    saved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeUI(saved);
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    if (!localStorage.getItem('boss-theme')) {
      const next = e.matches ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', next);
      updateThemeUI(next);
    }
  });
}

function updateThemeUI(theme) {
  const isDark = theme === 'dark';
  document.getElementById('themeIcon').innerHTML = isDark
    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
  document.getElementById('themeLabel').textContent = isDark ? '☀️ 亮色' : '🌙 暗色';
}

function clearLog() {
  document.getElementById('logArea').innerHTML = '<div class="log-empty"><div class="empty-icon">📝</div><div>等待操作...</div></div>';
}


function loadConfig() {
  fetch('/api/config').then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(cfg => {
    config = cfg.config || cfg;
    // 填充所有默认值
    if (!config.browser) config.browser = {};
    if (!config.login) config.login = {};
    if (!config.rate_limit) config.rate_limit = {};
    if (!config.retry) config.retry = {};
    config.browser = Object.assign({headless:false,viewport_width:1280,viewport_height:800,page_load_timeout:30,custom_user_agent:'',proxy:''}, config.browser);
    config.login = Object.assign({wait_timeout:300,clear_cookies_on_failure:true}, config.login);
    config.rate_limit = Object.assign({enabled:true,max_per_hour:30,max_per_day:100}, config.rate_limit);
    config.retry = Object.assign({max_attempts:3,base_delay:2,backoff_factor:2}, config.retry);
    if (!config.ai) config.ai = {};
    config.ai = Object.assign({enabled:false,api_key:'',api_base:'https://apihub.agnes-ai.com/v1',model:'agnes-2.5-flash',match_threshold:70}, config.ai);
    if (!config.resume) config.resume = {};
    config.resume = Object.assign({school:'',major:'',degree:'',skills:[],experience:'',target_position:'',self_intro:''}, config.resume);
    if (!config.accounts || !config.accounts.length) {
      config.accounts = [{name:'主账号',enabled:true,cookie_file:'zhipin_cookies.json',image_files:[],message_interval_min:3,message_interval_max:8,jobs:[{enabled:true,city:'上海',query:'数据分析',scroll_pages:5,greeting_message:defaultGreeting}]}];
    }
    // 填充每个账号和岗位的默认值
    config.accounts.forEach(function(acc) {
      acc.enabled = acc.enabled !== false;
      acc.cookie_file = acc.cookie_file || 'zhipin_cookies.json';
      acc.image_files = acc.image_files || [];
      acc.message_interval_min = acc.message_interval_min ?? 3;
      acc.message_interval_max = acc.message_interval_max ?? 8;
      (acc.jobs || []).forEach(function(job) {
        job.enabled = job.enabled !== false;
        job.city = job.city || '上海';
        job.query = job.query || '';
        job.scroll_pages = job.scroll_pages || 5;
        job.greeting_message = job.greeting_message || defaultGreeting;
      });
    });
    renderAccounts();
    renderAccountConfig();
    renderAdvSettings();
    renderAiConfig();
    renderJobs();
    updateSbarJobs();
    refreshImageList();
    addLog('SUCCESS', '配置已加载');
  }).catch(function(e){console.error('loadConfig:',e);addLog('ERROR','加载配置失败: '+e.message);});
}

function saveConfig() {
  if (!config) {
    addLog('ERROR', '配置未加载，请刷新页面');
    return Promise.reject(new Error('配置未加载'));
  }
  return fetch('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:config})})
    .then(r=>{if(!r.ok)throw new Error('保存失败: '+r.status);return r.json()})
    .then(d=>{if(d.status!=='ok')throw new Error(d.message||'保存失败');addLog('SYSTEM','配置已保存')})
    .catch(e=>{addLog('ERROR', '保存配置失败: '+e.message);throw e});
}

function renderAccounts() {
  const c = document.getElementById('accountTabs');
  const badge = document.getElementById('accBadge');
  c.innerHTML = config.accounts.map((a,i) =>
    '<div class="account-tab'+(i===activeAccountIdx?' active':'')+'" onclick="switchAccount('+i+')">'+escHtml(a.name||'未命名')+'<span class="badge">'+(a.jobs||[]).length+'</span></div>'
  ).join('');
  if (badge) badge.textContent = config.accounts.length;
}


function setEl(id, cls) { var e = document.getElementById(id); if (e) e.className = cls; }
function setVal(id, v) { var e = document.getElementById(id); if (e) e.value = v; }
function setPlh(id, v) { var e = document.getElementById(id); if (e) e.placeholder = v; }

function renderAdvSettings() {
  const b = config.browser || {};
  setEl('advHeadless', 'toggle-switch' + (b.headless ? ' on' : ''));
  setVal('advViewportW', b.viewport_width ?? 1280);
  setVal('advViewportH', b.viewport_height ?? 800);
  setVal('advTimeout', b.page_load_timeout ?? 30);
  setVal('advUserAgent', b.custom_user_agent || '');
  setPlh('advUserAgent', '留空自动');
  setVal('advProxy', b.proxy || '');
  setPlh('advProxy', 'http://...');

  const rl = config.rate_limit || {};
  setEl('advRateLimit', 'toggle-switch' + (rl.enabled !== false ? ' on' : ''));
  setVal('advRatePerHour', rl.max_per_hour ?? 30);
  setVal('advRatePerDay', rl.max_per_day ?? 100);

  const lg = config.login || {};
  setVal('advLoginWait', lg.wait_timeout ?? 300);
  setEl('advClearCookies', 'toggle-switch' + (lg.clear_cookies_on_failure !== false ? ' on' : ''));

  const rt = config.retry || {};
  setVal('advRetryAttempts', rt.max_attempts ?? 3);
  setVal('advRetryDelay', rt.base_delay ?? 2);
  setVal('advRetryBackoff', rt.backoff_factor ?? 2);
}

function toggleAdvSection() {
  const btn = document.getElementById('advToggle');
  const section = document.getElementById('advSection');
  section.classList.toggle("open");
  btn.classList.toggle("open");
}

function toggleAdvBool(key) {
  if (key === "headless") {
    if (!config.browser) config.browser = {};
    config.browser.headless = !config.browser.headless;
    setEl('advHeadless', 'toggle-switch' + (config.browser.headless ? ' on' : ''));
  } else if (key === "rate_limit_enabled") {
    if (!config.rate_limit) config.rate_limit = {};
    config.rate_limit.enabled = !config.rate_limit.enabled;
    setEl('advRateLimit', 'toggle-switch' + (config.rate_limit.enabled !== false ? ' on' : ''));
  } else if (key === "clear_cookies") {
    if (!config.login) config.login = {};
    config.login.clear_cookies_on_failure = !config.login.clear_cookies_on_failure;
    setEl('advClearCookies', 'toggle-switch' + (config.login.clear_cookies_on_failure !== false ? ' on' : ''));
  }
  saveConfig();
}

function onAdvChange() {
  if (!config.browser) config.browser = {};
  config.browser.headless = document.getElementById('advHeadless').classList.contains('on');
  config.browser.viewport_width = parseInt(document.getElementById('advViewportW').value) || 1280;
  config.browser.viewport_height = parseInt(document.getElementById('advViewportH').value) || 800;
  config.browser.page_load_timeout = parseInt(document.getElementById('advTimeout').value) || 30;
  config.browser.custom_user_agent = document.getElementById('advUserAgent').value;
  config.browser.proxy = document.getElementById('advProxy').value;

  if (!config.rate_limit) config.rate_limit = {};
  config.rate_limit.enabled = document.getElementById('advRateLimit').classList.contains('on');
  config.rate_limit.max_per_hour = parseInt(document.getElementById('advRatePerHour').value) || 30;
  config.rate_limit.max_per_day = parseInt(document.getElementById('advRatePerDay').value) || 100;

  if (!config.login) config.login = {};
  config.login.wait_timeout = parseInt(document.getElementById('advLoginWait').value) || 300;
  config.login.clear_cookies_on_failure = document.getElementById('advClearCookies').classList.contains('on');

  if (!config.retry) config.retry = {};
  config.retry.max_attempts = parseInt(document.getElementById('advRetryAttempts').value) || 3;
  config.retry.base_delay = parseFloat(document.getElementById('advRetryDelay').value) || 2.0;
  config.retry.backoff_factor = parseFloat(document.getElementById('advRetryBackoff').value) || 2.0;

  // Message interval from advanced settings
  var _acc = config.accounts[activeAccountIdx];
  if (_acc) {
    _acc.message_interval_min = parseInt(document.getElementById('advMsgIntervalMin').value) || 3;
    _acc.message_interval_max = parseInt(document.getElementById('advMsgIntervalMax').value) || 8;
  }
  saveConfig();

}


function renderAccountConfig() {
  const a = config.accounts[activeAccountIdx];
  if (!a) return;
  document.getElementById('accName').value = a.name||'主账号';
  document.getElementById('accEnabled').className = 'toggle-switch'+(a.enabled!==false?' on':'');
  document.getElementById('accCookie').value = a.cookie_file||'zhipin_cookies.json';
  var _m1 = document.getElementById('msgIntervalMin');
  if (_m1) _m1.value = (a.message_interval_min !== undefined && a.message_interval_min !== null) ? a.message_interval_min : 3;
  var _m2 = document.getElementById('msgIntervalMax');
  if (_m2) _m2.value = (a.message_interval_max !== undefined && a.message_interval_max !== null) ? a.message_interval_max : 8;
  renderImageChips();
  renderImageGrid();
}

function renderJobs() {
  const a = config.accounts[activeAccountIdx];
  if (!a) return;
  const c = document.getElementById('jobList');
  if (!a.jobs || !a.jobs.length) {
    c.innerHTML = '<div class="empty-state"><div class="empty-icon">📋</div><div class="empty-title">暂无岗位</div><div class="empty-desc">点击上方「+ 添加岗位」按钮添加</div></div>';
    return;
  }
  c.innerHTML = a.jobs.map((j,i) =>
    '<div class="job-item">'+
      '<span class="job-toggle toggle-switch'+(j.enabled!==false?' on':'')+'" onclick="event.stopPropagation();toggleJob('+i+')"></span>'+
      '<div class="job-info" onclick="editJob('+i+')">'+
        '<div class="job-query">'+escHtml(j.query||'')+'</div>'+
        '<div class="job-city">'+escHtml(j.city||'')+(j.scroll_pages?' · '+j.scroll_pages+'页':'')+'</div>'+
      '</div>'+
      '<span class="job-badge">'+(j.city||'')+'</span>'+
      '<span class="job-del" onclick="event.stopPropagation();deleteJob('+i+')" title="删除">✕</span>'+
    '</div>'
  ).join('');
}

function updateSbarJobs() {
  const a = config.accounts[activeAccountIdx];
  const el = document.getElementById('sbarJobs');
  const badge = document.getElementById('sbarJobCount');
  if (a && a.jobs && a.jobs.length) {
    if (badge) badge.textContent = a.jobs.length;
    el.innerHTML = a.jobs.map((j,i) => '<div class="sbar-job-item" onclick="editJob('+i+')"><span class="sbar-job-query">'+escHtml(j.query||'')+'</span><span class="sbar-job-city">'+escHtml(j.city||'')+'</span></div>').join('');
  } else {
    if (badge) badge.textContent = '0';
    el.innerHTML = '<span style="color:var(--fg-3rd);font-size:10px;padding:8px 0;display:block;text-align:center">暂无岗位，点击上方添加</span>';
  }
}

function renderImageGrid() {
  const grid = document.getElementById('imageGrid');
  const a = config.accounts[activeAccountIdx];
  if (!a) return;
  const selected = a.image_files || [];
  if (!availableImages.length) {
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:16px;color:var(--fg-3rd);font-size:11px">\u6682\u65e0\u56fe\u7247\uff0c\u70b9\u51fb\u4e0a\u4f20</div>';
    return;
  }
  grid.innerHTML = availableImages.map(function(f) {
    var checked = selected.includes(f);
    var enc = escJs(f);
    var name = f.replace('dashboard/', '');
    return '<div class="image-grid-item' + (checked ? ' checked' : '') + '" onclick="toggleImageSelect(\'' + enc + '\')">' +
      '<div class="img-del-btn" onclick="event.stopPropagation();deleteImageFile(\'' + enc + '\')" title="\u5220\u9664\u6b64\u56fe\u7247">\u2716</div>' +
      '<img src="/' + f + '" alt="' + enc + '" loading="lazy" onerror="this.style.display=\'none\'">' +
      '<div class="check-overlay">\u2713</div>' +
      '<div class="img-name">' + escHtml(name) + '</div>' +
    '</div>';
  }).join('');
  updateImageCountBadge();
}

function toggleImageSelect(name) { name = decodeURIComponent(name);
  const a = config.accounts[activeAccountIdx];
  if (!a) return;
  if (!a.image_files) a.image_files = [];
  const idx = a.image_files.indexOf(name);
  if (idx >= 0) { a.image_files.splice(idx, 1); }
  else { a.image_files.push(name); }
  renderImageGrid();
  renderImageChips();
  saveConfig();
}

function renderImageChips() {
  const a = config.accounts[activeAccountIdx];
  const el = document.getElementById('imageChips');
  if (!a || !a.image_files || !a.image_files.length) {
    el.innerHTML = '';
    updateImageCountBadge();
    return;
  }
  el.innerHTML = a.image_files.map(f =>
    '<span class="chip">'+escHtml(f.replace('dashboard/',''))+'<span class="chip-remove" onclick="removeImage(\''+escJs(f)+'\')">✕</span></span>'
  ).join('');
  updateImageCountBadge();
}

function updateImageCountBadge() {
  const a = config.accounts[activeAccountIdx];
  const badge = document.getElementById('imageCountBadge');
  if (badge) badge.textContent = (a && a.image_files) ? a.image_files.length : 0;
}

function removeImage(name) {
  // 委托给 deleteImageFile 统一处理
  deleteImageFile(name);
}

function deleteImageFile(name) { 
  name = decodeURIComponent(name);
  if (!confirm('确定删除图片文件吗？这将从服务器上彻底删除此图片。')) return;
  // 构造请求体，支持 dashboard/ 前缀或纯文件名
  const reqPath = name.startsWith('dashboard/') ? name : 'dashboard/' + name.replace(/^dashboard[\\/]/, '');
  fetch('/api/images/delete', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:reqPath})
  }).then(r=>r.json()).then(data => {
    if (data.status === 'ok') {
      addLog('INFO', '已删除图片文件: ' + name);
      // 从当前账号的image_files中移除
      const a = config.accounts[activeAccountIdx];
      if (a && a.image_files) {
        a.image_files = a.image_files.filter(f => {
          const fName = f.replace('dashboard/', '').replace('dashboard\\', '');
          const delName = name.replace('dashboard/', '').replace('dashboard\\', '');
          return fName !== delName;
        });
      }
      // 从所有账号的image_files中移除
      for (const acc of config.accounts) {
        if (acc && acc.image_files) {
          acc.image_files = acc.image_files.filter(f => {
            const fName = f.replace('dashboard/', '').replace('dashboard\\', '');
            const delName = name.replace('dashboard/', '').replace('dashboard\\', '');
            return fName !== delName;
          });
        }
      }
      saveConfig(); // 持久化保存
      refreshImageList();
    } else {
      addLog('ERROR', '删除失败: ' + (data.message||''));
    }
  }).catch(e => addLog('ERROR', '删除异常: ' + e.message));
}

function deleteAllSelectedImages() {
  const a = config.accounts[activeAccountIdx];
  if (!a || !a.image_files || !a.image_files.length) {
    addLog('INFO', '没有已选的图片需要删除');
    return;
  }
  const count = a.image_files.length;
  if (!confirm('确定删除所有已选的 ' + count + ' 张图片文件吗？这将从服务器上彻底删除这些图片。')) return;
  const filesToDelete = [...a.image_files];
  let deleted = 0;
  let failed = 0;
  const promises = filesToDelete.map(f => {
    return fetch('/api/images/delete', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({path:f})
    }).then(r=>r.json()).then(data => {
      if (data.status === 'ok') deleted++;
      else failed++;
    }).catch(() => failed++);
  });
  Promise.all(promises).then(() => {
    addLog('INFO', '批量删除完成: ' + deleted + ' 成功, ' + failed + ' 失败');
    // 从所有账号中移除已删除的图片
    for (const acc of config.accounts) {
      if (acc && acc.image_files) {
        acc.image_files = acc.image_files.filter(f => !filesToDelete.includes(f));
      }
    }
    saveConfig();
    refreshImageList();
  });
}

function deleteAllImages() {
  if (!confirm('确定删除所有图片文件吗？此操作不可恢复！')) return;
  fetch('/api/images/delete', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({delete_all:true})
  }).then(r=>r.json()).then(data => {
    if (data.status === 'ok') {
      addLog('INFO', '已删除全部 ' + (data.deleted || 0) + ' 张图片');
      for (const acc of config.accounts) {
        if (acc && acc.image_files) {
          acc.image_files = [];
        }
      }
      saveConfig();
      refreshImageList();
    } else {
      addLog('ERROR', '删除失败: ' + (data.message||''));
    }
  }).catch(e => addLog('ERROR', '删除异常: ' + e.message));
}

function handleImageUpload(event) {
  const files = event.target.files;
  if (!files || !files.length) return;
  const formData = new FormData();
  for (let f of files) { formData.append('files', f); }
  fetch('/api/upload/images', { method:'POST', body:formData })
    .then(r=>r.json())
    .then(data => {
      if (data.status === 'ok') {
        addLog('INFO', '已上传 ' + data.files.length + ' 张图片');
        const a = config.accounts[activeAccountIdx];
        if (a) {
          if (!a.image_files) a.image_files = [];
          for (let f of data.files) { if (!a.image_files.includes(f)) { a.image_files.push(f); } }
        }
        saveConfig(); // 持久化保存配置
        refreshImageList();
      } else { addLog('ERROR', '上传失败: ' + (data.message||'')); }
    })
    .catch(e => addLog('ERROR', '上传异常: ' + e.message));
  event.target.value = '';
}


function cleanupStaleImages() {
  fetch('/api/images/list')
    .then(r => r.json())
    .then(data => {
      if (data.status !== 'ok') return;
      const existingImages = data.images || [];
      for (const acc of config.accounts) {
        if (acc && acc.image_files && acc.image_files.length) {
          acc.image_files = acc.image_files.filter(f => existingImages.includes(f));
        }
      }
      saveConfig();
    })
    .catch(() => {});
}

function refreshImageList() {
  cleanupStaleImages();
  fetch('/api/images/list')
    .then(r=>r.json())
    .then(data => { if (data.status === 'ok') { availableImages = data.images; renderImageGrid(); renderImageChips(); } })
    .catch(()=>{});
}



function switchAccount(i) { activeAccountIdx = i; renderAccounts(); renderAccountConfig(); renderJobs(); updateSbarJobs(); }

function onAccChange() {
  onAdvChange();
  const a = config.accounts[activeAccountIdx];
  if (!a) return;
  a.name = document.getElementById('accName').value;
  a.cookie_file = document.getElementById('accCookie').value;
  var _mi1 = document.getElementById('msgIntervalMin');
  var _mi2 = document.getElementById('msgIntervalMax');
  if (_mi1) a.message_interval_min = parseFloat(_mi1.value) || 3;
  if (_mi2) a.message_interval_max = parseFloat(_mi2.value) || 8;
  saveConfig();
}

function toggleAccEnabled() {
  const a = config.accounts[activeAccountIdx];
  if (!a) return;
  a.enabled = a.enabled === false;
  renderAccountConfig();
  saveConfig();
}

function toggleJob(i) {
  const a = config.accounts[activeAccountIdx];
  if (!a || !a.jobs || !a.jobs[i]) return;
  a.jobs[i].enabled = a.jobs[i].enabled === false;
  renderJobs();
  updateSbarJobs();
  saveConfig();
}

let editingJobIdx = -1;

function addJob() {
  editingJobIdx = -1;
  showJobModal({enabled:true,city:'上海',query:'数据分析',scroll_pages:5,greeting_message:defaultGreeting});
}

function editJob(i) {
  const a = config.accounts[activeAccountIdx];
  if (!a || !a.jobs || !a.jobs[i]) return;
  editingJobIdx = i;
  showJobModal(Object.assign({}, a.jobs[i]));
}

function showJobModal(job) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'jobModal';
  overlay.innerHTML =
    '<div class="modal">'+
      '<h3>'+(editingJobIdx>=0?'编辑岗位':'添加岗位')+'</h3>'+
      '<div class="modal-field"><label>城市</label><input id="modalCity" value="'+escHtml(job.city||'')+'" placeholder="例如: 上海"></div>'+
      '<div class="modal-field"><label>搜索关键词</label><input id="modalQuery" value="'+escHtml(job.query||'')+'" placeholder="例如: AI产品经理"></div>'+
      '<div class="modal-field"><label>翻页数</label><input id="modalPages" type="number" value="'+(job.scroll_pages||5)+'" min="1" max="20"></div>'+
      '<div class="modal-field"><label>打招呼消息</label><textarea id="modalGreeting" placeholder="输入自定义打招呼消息" style="min-height:80px">'+escHtml(job.greeting_message||defaultGreeting)+'</textarea></div>'+
      '<div class="modal-actions">'+
        '<button class="btn btn-primary" onclick="saveJobModal()">'+(editingJobIdx>=0?'保存':'添加')+'</button>'+
        '<button class="btn btn-cancel" onclick="closeJobModal()">取消</button>'+
      '</div>'+
    '</div>';
  document.body.appendChild(overlay);
}

function closeJobModal() {
  const m = document.getElementById('jobModal');
  if (m) m.remove();
}

function saveJobModal() {
  const city = document.getElementById('modalCity').value.trim();
  const query = document.getElementById('modalQuery').value.trim();
  const pages = parseInt(document.getElementById('modalPages').value) || 5;
  const greeting = document.getElementById('modalGreeting').value.trim() || defaultGreeting;
  if (!city || !query) { addLog('ERROR','城市和关键词不能为空'); return; }
  const a = config.accounts[activeAccountIdx];
  if (!a) return;
  if (!a.jobs) a.jobs = [];
  const job = { enabled:true, city, query, scroll_pages:pages, greeting_message:greeting };
  if (editingJobIdx >= 0 && editingJobIdx < a.jobs.length) {
    a.jobs[editingJobIdx] = job;
    addLog('INFO', '岗位已更新: ' + query);
  } else {
    a.jobs.push(job);
    addLog('INFO', '岗位已添加: ' + query);
  }
  closeJobModal();
  renderJobs();
  updateSbarJobs();
  saveConfig();
}

function deleteJob(i) {
  if (!confirm('确定删除此岗位？')) return;
  const a = config.accounts[activeAccountIdx];
  if (!a || !a.jobs) return;
  a.jobs.splice(i, 1);
  renderJobs();
  updateSbarJobs();
  saveConfig();
  addLog('INFO', '岗位已删除');
}

function addAccount() {
  fetch('/api/config/accounts', { method:'POST' })
    .then(r=>r.json())
    .then(data => {
      if (data.status === 'ok') {
        config.accounts = data.accounts;
        activeAccountIdx = config.accounts.length - 1;
        renderAccounts();
        renderAccountConfig();
        renderJobs();
        updateSbarJobs();
        addLog('INFO', '已添加新账号');
      } else { addLog('ERROR', '添加账号失败'); }
    })
    .catch(e => addLog('ERROR', '添加账号异常: ' + e.message));
}

function deleteAccount(i) {
  if (!confirm('确定删除账号「' + (config.accounts[i]?.name || '账号'+(i+1)) + '」？')) return;
  onAccChange();
  fetch('/api/config/accounts/' + i, { method:'DELETE' })
    .then(r=>r.json())
    .then(data => {
      if (data.status === 'ok') {
        config.accounts = data.accounts;
        if (activeAccountIdx >= config.accounts.length) activeAccountIdx = Math.max(0, config.accounts.length - 1);
        renderAccounts();
        renderAccountConfig();
        renderJobs();
        updateSbarJobs();
        addLog('INFO', '已删除账号');
      } else { addLog('ERROR', '删除账号失败'); }
    })
    .catch(e => addLog('ERROR', e.message));
}

function startAll() {
  const btn = document.getElementById('btnStartAll');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 启动中...'; }
  // 先保存配置
  saveConfig()
    .then(() => {
      // 先重置调度器状态
      return fetch('/api/scheduler/reset', { method:'POST' });
    })
    .then(r => r.json())
    .then(data => {
      if (data.status !== 'ok') {
        throw new Error('调度器重置失败: ' + (data.message || '未知错误'));
      }
      // 稍微延迟确保状态已完全重置
      setTimeout(() => {
        if (socket && socket.connected) {
          socket.emit('start_all');
          addLog('SYSTEM','正在启动所有任务...');
        } else {
          addLog('ERROR', 'WebSocket 未连接，请刷新页面重试');
          if (btn) { btn.disabled = false; btn.textContent = '▶ 启动'; btn.style.display = ''; }
        }
      }, 500);
    })
    .catch(e => {
      addLog('ERROR', '启动失败: ' + e.message);
      if (btn) { btn.disabled = false; btn.textContent = '▶ 启动'; btn.style.display = ''; }
    });
}

function stopAll() {
  socket.emit('stop_all');
  addLog('SYSTEM','正在停止所有任务...');
  const btn = document.getElementById('btnStartAll');
  if (btn) { btn.disabled = false; btn.textContent = '▶ 启动'; btn.style.display = ''; }
  const stopBtn = document.getElementById('btnStopAll');
  if (stopBtn) { stopBtn.style.display = 'none'; }
  // 也重置状态点
  const dot = document.getElementById('sbarDot');
  if (dot) dot.className = 'status-dot idle';
  const st = document.getElementById('sbarStatus');
  if (st) st.textContent = '就绪';
}

function confirmLogin() { socket.emit('confirm_login'); }
function doConfirmLogin() {
  document.getElementById('loginModal').classList.remove('active');
  socket.emit('confirm_login');
  addLog('SYSTEM', '已确认登录，继续执行...');
}

function checkLogin() { socket.emit('check_login'); }

function setControls(running) {
  const s=document.getElementById('btnStartAll'),p=document.getElementById('btnStopAll'),cl=document.getElementById('btnConfirmLogin'),dot=document.getElementById('sbarDot'),st=document.getElementById('sbarStatus');
  if(s) { s.style.display=running?'none':''; s.disabled=false; s.textContent='▶ 启动'; }
  if(p) { p.style.display=running?'':'none'; }
  if(cl) { cl.style.display=running?'':'none'; }
  if(dot) dot.className='status-dot'+(running?' running':' idle');
  if(st) st.textContent=running?'运行中':'就绪';
}

function updateStats() {
  const t=document.getElementById('statTotal'),a=document.getElementById('statApplied'),s=document.getElementById('statSkipped');
  if(t) t.textContent=stats.total; if(a) a.textContent=stats.applied; if(s) s.textContent=stats.skipped;
}

function escHtml(t){const d=document.createElement('div');d.textContent=t;return d.innerHTML;}
function escAttr(t){return (t||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function escJs(t){return encodeURIComponent(t||'').replace(/%2F/g,'/').replace(/%20/g,' ');}

function addLog(level,message){
  const area=document.getElementById('logArea');
  const empty=area.querySelector('.log-empty');
  if(empty) empty.remove();
  const div=document.createElement('div');div.className='log-entry';
  const ts=new Date().toLocaleTimeString();
  div.innerHTML='<span class="log-time">'+ts+'</span><span class="log-message log-'+level+'">'+escHtml(message)+'</span>';
  area.appendChild(div);
  area.scrollTop=area.scrollHeight;
  while(area.children.length>300) area.removeChild(area.firstChild);
}


function resetScheduler() {
  fetch('/api/scheduler/reset', { method:'POST' })
    .then(r=>r.json())
    .then(data => {
      if (data.status === 'ok') {
        setControls(false);
      }
    })
    .catch(()=>{});
}

socket.on('connect',()=>{addLog('SYSTEM','WebSocket 已连接');document.getElementById('connStatus').textContent='已连接';resetScheduler();});
socket.on('disconnect',()=>{addLog('ERROR','WebSocket 断开');document.getElementById('connStatus').textContent='已断开';});
socket.on('bot_log',(data)=>{if(data&&data.message) addLog('INFO',data.message);});
socket.on('bot_progress',(data)=>{
  if(data.total!==undefined) stats.total=data.total;
  if(data.applied!==undefined) stats.applied=data.applied;
  if(data.skipped!==undefined) stats.skipped=data.skipped;
  updateStats();
});
socket.on('bot_status',(data)=>{setControls(data.running);if(!data.running)document.getElementById('currentTaskLabel').textContent='';});
socket.on('scheduler_status',(data)=>{
  setControls(data.running);
  const lbl=document.getElementById('currentTaskLabel');
  if(data.current&&lbl) lbl.textContent=data.current.account+' / '+(data.current.query?data.current.query:'')+'('+(data.current.city?data.current.city:'')+')';
  else if(!data.running&&lbl) lbl.textContent='';
  if(!data.running){
    const btn=document.getElementById('btnStartAll');
    if(btn){btn.disabled=false;btn.textContent='▶ 启动';btn.style.display='';}
    const stopBtn=document.getElementById('btnStopAll');
    if(stopBtn)stopBtn.style.display='none';
  }
});
socket.on('bot_login',()=>{document.getElementById('btnConfirmLogin').disabled=false;});
socket.on('login_result',(data)=>{if(data.success)addLog('SUCCESS','登录状态正常');else addLog('ERROR','未登录');});


socket.on('login_required', (data) => {
  const modal = document.getElementById('loginModal');
  if (!modal) return;
  const desc = document.getElementById('loginModalDesc');
  if (data && data.message) {
    desc.textContent = data.message;
  } else {
    desc.textContent = '登录已过期或未登录，请在浏览器中完成登录，然后点击下方按钮继续。';
  }
  modal.style.display = 'flex';
  modal.classList.add('active');
  addLog('WARN', '需要登录：请在浏览器中登录后点击确认');
});

loadTheme();
loadConfig();

function closeLoginModal() {
  const modal = document.getElementById("loginModal");
  if (modal) {
    modal.style.display = "none";
    modal.classList.remove("active");
  }
  if (socket) socket.emit("stop_login_modal");
}


function uploadCookieFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  fetch('/api/cookies/upload', { method:'POST', body: formData })
    .then(r=>r.json())
    .then(data => {
      if (data.status === 'ok') {
        addLog('SUCCESS', 'Cookie 已上传: ' + file.name);
        config.accounts[activeAccountIdx].cookie_file = data.filename || file.name;
        renderAccountConfig();
        saveConfig();
      } else {
        addLog('ERROR', 'Cookie 上传失败: ' + (data.message || ''));
      }
    })
    .catch(e => addLog('ERROR', 'Cookie 上传失败: ' + e.message));
  event.target.value = '';
}

function deleteCookieFile() {
  const filename = document.getElementById("accCookie").value || "zhipin_cookies.json";
  if (!confirm("确定删除 Cookie 文件 \"" + filename + "\" 吗？")) return;
  fetch("/api/cookies/delete", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({filename: filename})
  }).then(r=>r.json()).then(data => {
    if (data.status === "ok") {
      addLog("INFO", "已删除 Cookie 文件: " + filename);
      config.accounts[activeAccountIdx].cookie_file = "";
      renderAccountConfig();
      saveConfig();
    } else {
      addLog("ERROR", "删除失败: " + (data.message||""));
    }
  }).catch(e => addLog("ERROR", "删除异常: " + e.message));
}


