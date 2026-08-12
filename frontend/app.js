const API = "/api/v1";

// ============================================================
// 认证管理
// ============================================================
let AUTH_TOKEN = localStorage.getItem("auth_token") || "";
let AUTH_USER = JSON.parse(localStorage.getItem("auth_user") || "null");

// 游客 ID：每个浏览器唯一，不登录也能用，数据互不干扰
function getGuestId() {
    var id = localStorage.getItem("guest_id");
    if (!id) {
        id = "guest_" + Math.random().toString(36).slice(2, 10);
        localStorage.setItem("guest_id", id);
    }
    return id;
}

function getUserId() {
    return AUTH_USER ? AUTH_USER.user_id : getGuestId();
}
function getUserName() {
    return AUTH_USER ? AUTH_USER.name : "游客";
}
function getAuthHeaders() {
    var headers = { "Content-Type": "application/json" };
    if (AUTH_TOKEN) headers["Authorization"] = "Bearer " + AUTH_TOKEN;
    return headers;
}
function saveAuth(token, user) {
    AUTH_TOKEN = token;
    AUTH_USER = user;
    localStorage.setItem("auth_token", token);
    localStorage.setItem("auth_user", JSON.stringify(user));
    updateUserDisplay();
    closeAuthModal();
    // 生成新的 session，与登录用户绑定（清掉游客残留）
    window._userSessionId = "sess_" + user.user_id + "_" + Date.now();

    // 欢迎卡片
    var msgs = document.querySelector('.messages-inner');
    if (!msgs) return;
    msgs.innerHTML = '<div class="welcome-card"><div class="welcome-icon"><img src="/static/favicon.png" alt="" class="welcome-avatar"></div><div class="h2">' + getUserName() + '，欢迎使用AI智能管家</div><p class="welcome-desc">购物清单、膳食规划、家电调度、安防巡检 — 一个管家全搞定</p></div>';

    // 1.2 秒后管家主动打招呼（固定话术，不调 API，秒出）
    setTimeout(function() {
        var div = document.createElement("div");
        div.className = "msg assistant";
        div.innerHTML = '<div class="avatar"><img src="/static/favicon.png" style="width:36px;height:36px;border-radius:50%;object-fit:cover"></div><div class="bubble"></div>';
        msgs.appendChild(div);
        var bubble = div.querySelector(".bubble");
        scrollDown();

        var greeting = [
            "<strong>" + getUserName() + " 您好！我是您的家务AI管家</strong>",
            "",
            "我能帮您打理这些事：",
            "",
            "<strong>购物管理</strong> — 记录冰箱库存、一键生成购物清单、超市比价",
            "<strong>膳食规划</strong> — 根据现有食材推荐菜谱、定制一周菜单",
            "<strong>家电调度</strong> — 智能错峰运行，省电省钱",
            "<strong>维保提醒</strong> — 空调、洗碗机到期自动提醒",
            "<strong>安防巡检</strong> — 门窗监控、老人活动监测",
            "",
            "在开始之前，想先了解下您家的情况——",
            "<strong>请问您家里有几口人？有什么口味偏好吗？</strong>"
        ].join("<br>");

        bubble.innerHTML = greeting;
        scrollDown();
    }, 1200);
}
function logout() {
    if (!confirm("确定要退出登录吗？")) return;
    AUTH_TOKEN = "";
    AUTH_USER = null;
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    // 刷新页面，清空旧用户的聊天记录
    location.reload();
}
function updateUserDisplay() {
    var el = document.getElementById("userDisplay");
    if (el) {
        el.textContent = AUTH_USER ? getUserName() : "游客";
        el.className = "user-display" + (AUTH_USER ? " logged-in" : "");
        el.title = AUTH_USER ? "点击退出登录" : "游客模式 · 点击登录保存数据";
        el.onclick = AUTH_USER ? logout : showAuthModal;
    }
}
// 验证码
var _captchaId = "";
function refreshCaptcha() {
    fetch(API + "/auth/captcha")
        .then(function(r) { return r.json(); })
        .then(function(d) {
            _captchaId = d.captcha_id;
            var img = document.getElementById("regCaptchaImg");
            if (img) img.src = d.image;
            var input = document.getElementById("regCaptchaAnswer");
            if (input) input.value = "";
        })
        .catch(function() {
            var img = document.getElementById("regCaptchaImg");
            if (img) img.alt = "加载失败，点击重试";
        });
}

function showAuthModal() {
    document.getElementById("authModal").style.display = "flex";
    document.getElementById("authHint").style.display = "block";
    refreshCaptcha();
}
function closeAuthModal() {
    document.getElementById("authModal").style.display = "none";
}
function switchAuthTab(tab) {
    document.getElementById("tabLogin").className = "modal-tab" + (tab === "login" ? " active" : "");
    document.getElementById("tabRegister").className = "modal-tab" + (tab === "register" ? " active" : "");
    document.getElementById("loginForm").style.display = tab === "login" ? "block" : "none";
    document.getElementById("registerForm").style.display = tab === "register" ? "block" : "none";
    document.getElementById("loginError").textContent = "";
    document.getElementById("regError").textContent = "";
}
async function handleLogin(e) {
    e.preventDefault();
    var err = document.getElementById("loginError");
    err.textContent = "";
    try {
        var resp = await fetch(API + "/auth/login", {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({
                email: document.getElementById("loginEmail").value,
                password: document.getElementById("loginPassword").value
            })
        });
        var data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "登录失败");
        saveAuth(data.access_token, { user_id: data.user_id, name: data.name });
    } catch (ex) {
        err.textContent = ex.message;
    }
}
async function handleRegister(e) {
    e.preventDefault();
    var err = document.getElementById("regError");
    err.textContent = "";
    try {
        var resp = await fetch(API + "/auth/register", {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({
                email: document.getElementById("regEmail").value,
                name: document.getElementById("regName").value,
                password: document.getElementById("regPassword").value,
                family_size: 1,
                captcha_id: _captchaId,
                captcha_answer: document.getElementById("regCaptchaAnswer").value.trim()
            })
        });
        var data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "注册失败");
        saveAuth(data.access_token, { user_id: data.user_id, name: data.name });
    } catch (ex) {
        err.textContent = ex.message;
        refreshCaptcha();
    }
}

const AGENTS = {
  default: {
    name: "家务AI管家", icon: "favicon.png",
    desc: "购物·膳食·家电·维保·安防·事务 — 一个管家全搞定",
    chipGroups: [
      { label: "饮食料理", chips: ["看看冰箱里有什么","帮我规划一周菜谱","冰箱食材快过期了能做什么","帮我生成购物清单并比价"] },
      { label: "菜谱教程", chips: ["红烧肉怎么做","番茄炒蛋怎么做","牛肉怎么做"] },
      { label: "家居安防维保", chips: ["预约今晚错峰运行","检查家电维保状态","查看门口监控","今天有什么待办"] }
    ],
    placeholder: "需要我做什么？购物、菜谱、家电、安防...都可以",
    intent: "general", color: "primary"
  }
};

let isStreaming = false, activeAbort = null;
// 待确认的危险操作（安全护栏拦截后暂存）
let _pendingConfirmation = null;

document.addEventListener("DOMContentLoaded", () => {
  updateUserDisplay();
  updateGreeting();
  // 已登录用户刷新后显示个性化欢迎卡片
  if (AUTH_USER) {
    var inner = document.querySelector('.messages-inner');
    if (inner) {
      inner.innerHTML = '<div class="welcome-card"><div class="welcome-icon"><img src="/static/favicon.png" alt="" class="welcome-avatar"></div><div class="h2">' + getUserName() + '，欢迎使用AI智能管家</div><p class="welcome-desc">购物清单、膳食规划、家电调度、安防巡检 — 一个管家全搞定</p></div>';
    }
  }
  renderChips();
  initWorkflowBtns();
  initChipDelegation();
  initActionButtons();
  preloadVoices();
  updateStatusBar();
  autoRefreshAlerts();
});

function updateGreeting() {
  var h = new Date().getHours();
  var g = h >= 6 && h < 11 ? "早上好" : h >= 11 && h < 17 ? "下午好" : h >= 17 && h < 22 ? "晚上好" : "夜深了";
  var titleEl = document.querySelector(".welcome-card .h2");
  if (titleEl) titleEl.textContent = g + "，有什么可以帮您？";
}

function renderChips() {
  var chipsEl = document.getElementById("quickChips");
  if (!chipsEl) return;
  var groups = AGENTS["default"].chipGroups;
  chipsEl.innerHTML = groups.map(function(g) {
    return '<div class="chip-group"><span class="chip-group-label">' + g.label + '</span>'
      + g.chips.map(function(c) { return '<span class="chip" data-chip-text="' + c.replace(/"/g,"&quot;") + '">' + c + '</span>'; }).join('')
      + '</div>';
  }).join("");
}

function initChipDelegation() {
  var chipsEl = document.getElementById("quickChips");
  if (!chipsEl) return;
  chipsEl.addEventListener("click", function(e) {
    var chip = e.target.closest(".chip");
    if (!chip) return;
    var text = chip.dataset.chipText;
    if (text) { document.getElementById("userInput").value = text; sendMessage(); }
  });
}

function initWorkflowBtns() {
  document.querySelectorAll(".topbar-btn[data-wf]").forEach(function(btn) {
    btn.addEventListener("click", async function() {
      var type = this.dataset.wf;
      if (!type || isStreaming) return;
      this.disabled = true;
      var origText = this.textContent;
      this.textContent = "执行中...";
      typewriterCancel();
      var msgs = document.querySelector('.messages-inner');
      var div = document.createElement("div");
      div.className = "msg assistant";
      div.innerHTML = '<div class="avatar"><img src="/static/favicon.png" style="width:36px;height:36px;border-radius:50%;object-fit:cover"></div><div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>';
      msgs.appendChild(div);
      var streamEl = div.querySelector(".bubble");
      scrollDown();
      try {
        var resp = await fetch(API + "/agent/workflow/" + type + "?session_id=wf_" + Date.now(), { method: "POST", headers: getAuthHeaders() });
        var data = await resp.json();
        var text = (data.results && data.results.response) || data.response || "";
        if (text) {
          var tw = typewriterStart(streamEl, function(finalText) {
            addActionButtons(div, finalText, null, type);
          });
          tw.feed(text);
          tw.flush();
        } else {
          streamEl.innerHTML = renderMD("完成");
          addActionButtons(div, "", null, type);
        }
      } catch(e) {
        typewriterCancel();
        streamEl.innerHTML = "执行失败: " + escapeHtml(e.message);
      }
      this.disabled = false;
      this.textContent = origText;
      scrollDown();
    });
  });
}

var _alertPollTimer = null;

var _alertKeepAliveTimer = null;

function autoRefreshAlerts() {
  // 1. 启动时触发一次 daily_check 快速出结果
  var dashHeaders = getAuthHeaders();
  dashHeaders["X-User-ID"] = getUserId();
  fetch(API + '/dashboard/run/daily', { method: 'POST', headers: dashHeaders });

  // 2. 快速轮询（最多5次 × 8秒 = 40秒），检测到告警就停
  var tries = 0;
  function poll() {
    tries++;
    updateStatusBar().then(function() {
      if ((!window._alertItems || window._alertItems.length === 0) && tries < 5) {
        _alertPollTimer = setTimeout(poll, 8000);
      }
    });
  }
  _alertPollTimer = setTimeout(poll, 8000);

  // 3. 每天早上 8:00 自动触发一次 daily_check（不轮询，一天一次）
  if (_alertKeepAliveTimer) clearTimeout(_alertKeepAliveTimer);
  var now = new Date();
  var next8am = new Date(now);
  next8am.setHours(8, 0, 0, 0);
  if (now >= next8am) {
    // 今天 8 点已过 → 明天 8 点
    next8am.setDate(next8am.getDate() + 1);
  }
  var msUntil8am = next8am.getTime() - now.getTime();
  console.log("下次自动巡检: " + next8am.toLocaleString() + " (" + Math.round(msUntil8am / 3600000) + "小时后)");

  _alertKeepAliveTimer = setTimeout(function() {
    var h = getAuthHeaders();
    h["X-User-ID"] = getUserId();
    fetch(API + '/dashboard/run/daily', { method: 'POST', headers: h });
    setTimeout(function() { updateStatusBar(); }, 5000);
    // 每天一次，8 点触发后设下一次 24 小时后
    setInterval(function() {
      var h2 = getAuthHeaders();
      h2["X-User-ID"] = getUserId();
      fetch(API + '/dashboard/run/daily', { method: 'POST', headers: h2 });
      setTimeout(function() { updateStatusBar(); }, 5000);
    }, 86400000);
  }, msUntil8am);
}

async function updateStatusBar() {
  try {
    var headers = getAuthHeaders();
    headers["X-User-ID"] = getUserId();
    var alerts = await fetch(API + "/dashboard/alerts", { headers: headers }).then(function(r) { return r.json(); });
    var badge = document.getElementById("logoTaskBadge");
    // load dismissed alerts from localStorage (survives refresh)
    if (!window._dismissedAlerts) {
        try { window._dismissedAlerts = JSON.parse(localStorage.getItem("dismissedAlerts") || "[]"); }
        catch(e) { window._dismissedAlerts = []; }
    }
    var dismissed = window._dismissedAlerts;
    // clean up: remove dismissed items that no longer exist in fresh alerts
    window._dismissedAlerts = dismissed.filter(function(d) { return alerts.alerts.indexOf(d) !== -1; });
    localStorage.setItem("dismissedAlerts", JSON.stringify(window._dismissedAlerts));
    var alertItems = (alerts.alerts || []).filter(function(item) {
        return dismissed.indexOf(item) === -1;
    });
    if (alertItems.length > 0) {
        badge.textContent = alertItems.length;
        badge.style.display = "";
    } else {
        badge.style.display = "none";
    }
    window._alertItems = alertItems;
  } catch(e) {}
}

// event delegation: clicking welcome-icon shows alerts or "all clear" message
document.addEventListener("click", function(e) {
    var icon = e.target.closest(".welcome-icon");
    if (!icon) return;
    e.stopPropagation();
    if (window._alertItems && window._alertItems.length > 0) {
        showAlertDropdown(window._alertItems);
    } else {
        showAllClearToast();
    }
});

function showAllClearToast() {
    var old = document.getElementById("alertDropdown");
    if (old) { old.remove(); return; }
    var icon = document.querySelector(".welcome-icon");
    if (!icon) return;
    var rect = icon.getBoundingClientRect();
    var dd = document.createElement("div");
    dd.id = "alertDropdown";
    dd.className = "alert-dropdown";
    dd.innerHTML = '<div class="alert-dropdown-item all-clear" style="border:none;cursor:default;color:var(--text-secondary);text-align:center">暂无待办，一切正常</div>';
    dd.style.top = (rect.bottom + 8) + "px";
    dd.style.left = (rect.left + rect.width/2) + "px";
    document.body.appendChild(dd);
    setTimeout(function() { dd.classList.add("show"); }, 10);
    setTimeout(function() {
        if (dd.parentNode) { dd.classList.remove("show"); setTimeout(function() { dd.remove(); }, 200); }
    }, 2000);
    function close(e) {
        if (!dd.contains(e.target) && e.target !== icon && !icon.contains(e.target)) {
            dd.remove();
            document.removeEventListener("click", close);
        }
    }
    setTimeout(function() { document.addEventListener("click", close); }, 100);
}

function showAlertDropdown(items) {
    var old = document.getElementById("alertDropdown");
    if (old) { old.remove(); return; }
    var icon = document.querySelector(".welcome-icon");
    if (!icon) return;
    var rect = icon.getBoundingClientRect();
    var dd = document.createElement("div");
    dd.id = "alertDropdown";
    dd.className = "alert-dropdown";
    dd.innerHTML = '<div class="alert-dropdown-header">待办事项</div>' +
        items.map(function(item) { return '<div class="alert-dropdown-item" data-query="' + escapeHtml(item) + '">' + escapeHtml(item) + '</div>'; }).join("");
    dd.style.top = (rect.bottom + 8) + "px";
    dd.style.left = (rect.left + rect.width/2) + "px";
    document.body.appendChild(dd);
    dd.querySelectorAll(".alert-dropdown-item").forEach(function(el, idx) {
        el.addEventListener("click", function() {
            var query = this.dataset.query;
            if (window._alertItems && window._alertItems[idx]) {
                // track as dismissed so it won't reappear on refresh
                if (!window._dismissedAlerts) window._dismissedAlerts = [];
                window._dismissedAlerts.push(window._alertItems[idx]);
                localStorage.setItem("dismissedAlerts", JSON.stringify(window._dismissedAlerts));
                window._alertItems.splice(idx, 1);
                var badge = document.getElementById("logoTaskBadge");
                var count = window._alertItems.length;
                if (count > 0) {
                    badge.textContent = count;
                } else {
                    badge.style.display = "none";
                }
            }
            dd.remove();
            sendDirectQuery(query);
        });
    });
    setTimeout(function() { dd.classList.add("show"); }, 10);
    function close(e) {
        if (!dd.contains(e.target) && e.target !== icon && !icon.contains(e.target)) {
            dd.remove();
            document.removeEventListener("click", close);
        }
    }
    setTimeout(function() { document.addEventListener("click", close); }, 100);
}

async function sendDirectQuery(query) {
    if (!query || isStreaming) return;
    isStreaming = true;
    if (activeAbort) { activeAbort.abort(); activeAbort = null; }
    typewriterCancel();
    var msgs = document.querySelector('.messages-inner');
    var div = document.createElement("div");
    div.className = "msg assistant";
    div.innerHTML = '<div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>';
    msgs.appendChild(div);
    var streamEl = div.querySelector(".bubble");
    scrollDown();
    var tw = null;
    try {
        activeAbort = new AbortController();
        var resp = await fetch(API + "/agent/chat/stream", {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ session_id: (window._userSessionId || "sess_default"), user_id: getUserId(), message: query, intent: "general", stream: true }),
            signal: activeAbort.signal
        });
        if (!resp.ok) throw new Error("请求失败(" + resp.status + ")");
        var reader = resp.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        while (true) {
            var result = await reader.read();
            if (result.done) break;
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (!line.startsWith("data: ")) continue;
                try {
                    var d = JSON.parse(line.slice(6));
                    if (d.done) break;
                    if (d.video) { _pendingVideoHtml = d.video; continue; }
                    if (d.requires_confirmation) {
                        typewriterCancel();
                        div.classList.add("pending-confirm");
                        streamEl.innerHTML = renderMD("⚠️ " + (d.content || "有操作需要您的确认"));
                        addActionButtons(div, d.content || "", query);
                        setTimeout(function() {
                            showConfirmationDialog(d.pending_dangerous_calls || []);
                        }, 300);
                        isStreaming = false;
                        activeAbort = null;
                        return;
                    }
                    if (d.content) {
                        if (!tw) tw = typewriterStart(streamEl, function(finalText) {
                            addActionButtons(div, finalText, query);
                        });
                        tw.feed(d.content);
                    }
                } catch(e) {}
            }
        }
        if (tw) {
            tw.flush();
        } else {
            streamEl.innerHTML = renderMD("(空)");
            addActionButtons(div, "", query);
        }
    } catch(err) {
        if (err.name === "AbortError") { typewriterCancel(); div.remove(); return; }
        typewriterCancel();
        streamEl.innerHTML = "网络异常: " + escapeHtml(err.message);
        addActionButtons(div, "", query);
    }
    isStreaming = false;
    activeAbort = null;
    scrollDown();
}

async function sendMessage() {
  var input = document.getElementById("userInput");
  var text = input.value.trim();
  if (!text || isStreaming) return;
  input.value = ""; input.focus(); isStreaming = true;
  if (activeAbort) { activeAbort.abort(); activeAbort = null; }
  typewriterCancel();
  var msgs = document.querySelector('.messages-inner');
  msgs.innerHTML += '<div class="msg user"><div class="avatar">👤</div><div class="bubble">' + escapeHtml(text) + '</div>';
  var div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = '<div class="avatar"><img src="/static/favicon.png" style="width:36px;height:36px;border-radius:50%;object-fit:cover"></div><div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>';
  msgs.appendChild(div);
  var streamEl = div.querySelector(".bubble");
  scrollDown();
  var btn = document.getElementById("sendBtn");
  if (btn) btn.disabled = true;
  var tw = null;
  try {
    activeAbort = new AbortController();
    var resp = await fetch(API + "/agent/chat/stream", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ session_id: (window._userSessionId || "sess_default"), user_id: getUserId(), message: text, intent: "general", stream: true }),
      signal: activeAbort.signal
    });
    if (!resp.ok) throw new Error("请求失败(" + resp.status + ")");
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";
    while (true) {
      var result = await reader.read();
      if (result.done) break;
      buffer += decoder.decode(result.value, { stream: true });
      var lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (!line.startsWith("data: ")) continue;
        try {
          var d = JSON.parse(line.slice(6));
          if (d.done) break;
          if (d.video) { _pendingVideoHtml = d.video; continue; }
          if (d.requires_confirmation) {
            // 安全护栏拦截 → 显示确认弹窗
            typewriterCancel();
            div.classList.add("pending-confirm");
            streamEl.innerHTML = renderMD("⚠️ " + (d.content || "有操作需要您的确认"));
            addActionButtons(div, d.content || "", text);
            setTimeout(function() {
              showConfirmationDialog(d.pending_dangerous_calls || []);
            }, 300);
            isStreaming = false;
            activeAbort = null;
            return;
          }
          if (d.content) {
            if (!tw) tw = typewriterStart(streamEl, function(finalText) {
              addActionButtons(div, finalText, text);
            });
            tw.feed(d.content);
          }
        } catch(e) {}
      }
    }
    if (tw) {
      tw.flush();
    } else {
      streamEl.innerHTML = renderMD("(空)");
      addActionButtons(div, "", text);
    }
  } catch(err) {
    if (err.name === "AbortError") { typewriterCancel(); div.remove(); isStreaming = false; activeAbort = null; return; }
    typewriterCancel();
    streamEl.innerHTML = "网络异常: " + escapeHtml(err.message);
    addActionButtons(div, "", text);
  }
  if (btn) btn.disabled = false;
  isStreaming = false;
  activeAbort = null;
  scrollDown();
}

// 滚动节流：流式高频更新时最多 60fps
var _scrollPending = false;
function scrollDown() {
  if (_scrollPending) return;
  _scrollPending = true;
  requestAnimationFrame(function() {
    _scrollPending = false;
    var m = document.getElementById("messages");
    if (m) m.scrollTop = m.scrollHeight;
  });
}

// ====== 逐字打字机效果 ======
var _twTimer = null;
var _pendingVideoHtml = '';  // 视频卡片 HTML（独立于文本流，最后注入）

function typewriterCancel() {
  if (_twTimer) { clearTimeout(_twTimer); _twTimer = null; }
}

function typewriterStart(streamEl, onFinish) {
  typewriterCancel();
  var buf = '', pos = 0, done = false, finished = false;

  function tick() {
    if (finished) return;
    if (pos < buf.length) {
      var adv = 2 + Math.floor(Math.random() * 2);
      pos = Math.min(pos + adv, buf.length);
      if (streamEl) streamEl.innerHTML = renderMD(buf.slice(0, pos));
      scrollDown();
      if (pos >= buf.length && done) { finishUp(); return; }
    }
    _twTimer = setTimeout(tick, 30);
  }

  function finishUp() {
    if (finished) return;
    finished = true;
    typewriterCancel();
    // 先渲染文字，再注入视频卡片 HTML
    if (streamEl) {
      streamEl.innerHTML = renderMD(buf);
      if (_pendingVideoHtml) {
        streamEl.innerHTML += _pendingVideoHtml;
        _pendingVideoHtml = '';
      }
    }
    scrollDown();
    if (onFinish) onFinish(buf, streamEl);
  }

  _twTimer = setTimeout(tick, 20);

  return {
    feed: function(s) { buf += s; },
    flush: function() {
      done = true;
      if (pos >= buf.length) finishUp();
    },
    text: function() { return buf; }
  };
}

function escapeHtml(t) {
  var d = document.createElement("div");
  d.textContent = t || "";
  return d.innerHTML;
}


function stripVideoTable(text) {
  return text
    .replace(/🎬[\s\S]*?\n\n/g, '')
    .replace(/\|.*作者.*\|.*时长.*\|.*播放量.*\|[\s\S]*?\n\n/g, '')
    .replace(/\|.*视频.*\|.*\|.*\|/g, '');
}
function renderMD(t) {
  if (!t) return "";

  // 提取视频卡片 HTML（后端生成的受信内容，单独处理）
  var videoHtml = '';
  var clean = t.replace(/<!--VIDEOS-->([\s\S]*?)<!--\/VIDEOS-->/g, function(_, m) {
    videoHtml += m; return '';
  });
  clean = stripVideoTable(clean);


  // 去掉 bilibili 链接（已转为视频卡片）
  clean = clean.replace(/\[([^\]]*)\]\(https?:\/\/[^)]*bilibili[^)]*\)/g, '');
  // 去掉 --- 分隔线
  clean = clean.replace(/^---+\s*$/gm, '');

  var html;
  if (typeof marked !== 'undefined') {
    // marked 渲染（GFM: 表格/任务列表/删除线 全支持）
    marked.setOptions({ breaks: true, gfm: true });
    html = marked.parse(clean);
  } else {
    // 降级：简易 regex 渲染
    html = fallbackRenderMD(clean);
  }

  // DOMPurify 清洗（只允许安全标签，保留链接 target）
  if (typeof DOMPurify !== 'undefined') {
    html = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: ['p','br','strong','em','h1','h2','h3','h4','h5','h6',
        'ul','ol','li','a','code','pre','table','thead','tbody','tr','th','td',
        'blockquote','hr','img','del','input'],
      ALLOWED_ATTR: ['href','target','rel','src','alt','class','checked','type','disabled'],
    });
  }

  // 兜底去横线
  html = html.replace(/<hr\s*\/?>/gi, '');
  return html + videoHtml;
}

// 简易降级渲染（marked 未加载时使用）
function fallbackRenderMD(t) {
  var h = t;
  h = h.replace(/```(\w*)\n([\s\S]*?)```/g, function(_,l,c) { return '<pre><code>' + escapeHtml(c.trim()) + '</code></pre>'; });
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  h = h.replace(/\n\n/g, '</p><p>');
  h = h.replace(/\n/g, '<br>');
  if (!h.startsWith('<')) h = '<p>' + h + '</p>';
  h = h.replace(/<p>\s*<\/p>/g, '');
  return h;
}

// ====== 消息操作按钮：复制 · 朗读 · 赞 · 踩 · 重新生成 ======
var _speakingBtn = null;
var _sweetVoice = null;

// 预加载中文甜美女声
function preloadVoices() {
  if (!window.speechSynthesis) return;
  var voices = window.speechSynthesis.getVoices();
  if (voices.length > 0) {
    _sweetVoice = pickSweetVoice(voices);
  }
  // 部分浏览器异步加载语音列表
  window.speechSynthesis.onvoiceschanged = function() {
    var v = window.speechSynthesis.getVoices();
    if (!_sweetVoice) _sweetVoice = pickSweetVoice(v);
  };
}

function pickSweetVoice(voices) {
  // 优先级：甜美女声关键词匹配
  var femaleKeywords = ['Ting-Ting', 'Yaoyao', 'Tian Tian', 'Meijia', 'Xiaoxiao',
    'Yunxia', 'Xiaoyi', 'female', 'Female', 'woman', 'girl',
    'TingTing', 'YaoYao', 'Mei-Jia', 'Xiao Xiao', '小', '女', '佳', '甜'];
  var zhVoices = voices.filter(function(v) {
    return v.lang.indexOf('zh') === 0;
  });
  if (zhVoices.length === 0) zhVoices = voices.filter(function(v) {
    return v.lang.indexOf('zh') >= 0;
  });
  // 先匹配关键词
  for (var i = 0; i < femaleKeywords.length; i++) {
    for (var j = 0; j < zhVoices.length; j++) {
      if (zhVoices[j].name.indexOf(femaleKeywords[i]) !== -1) {
        return zhVoices[j];
      }
    }
  }
  // 降级：返回第一个中文语音
  if (zhVoices.length > 0) return zhVoices[0];
  // 再降级：尝试找任何 female 语音
  for (var k = 0; k < voices.length; k++) {
    if (voices[k].name.toLowerCase().indexOf('female') !== -1 ||
        voices[k].name.toLowerCase().indexOf('woman') !== -1) {
      return voices[k];
    }
  }
  return null;
}

function addActionButtons(msgDiv, fullText, userQuery, workflowType) {
  var existing = msgDiv.querySelector('.msg-actions');
  if (existing) existing.remove();
  if (userQuery) msgDiv.dataset.userQuery = userQuery;
  if (workflowType) msgDiv.dataset.workflowType = workflowType;
  msgDiv.dataset.originalText = fullText;

  // 先清除所有旧消息的重新生成按钮（只有最新一条可以重新生成）
  removeAllRegenerateButtons();

  var actions = document.createElement('div');
  actions.className = 'msg-actions';
  actions.innerHTML =
    '<button class="action-btn" data-action="copy" title="复制">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
    '</button>' +
    '<button class="action-btn" data-action="speak" title="朗读">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>' +
    '</button>' +
    '<button class="action-btn" data-action="like" title="喜欢">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>' +
    '</button>' +
    '<button class="action-btn" data-action="dislike" title="不喜欢">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10zM17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/></svg>' +
    '</button>' +
    '<button class="action-btn" data-action="regenerate" title="重新生成">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>' +
    '</button>';
  var bubble = msgDiv.querySelector('.bubble');
  if (bubble) bubble.appendChild(actions);
}

// 移除所有历史消息中的重新生成按钮（保留当前最新一条）
function removeAllRegenerateButtons() {
  var allRegenBtns = document.querySelectorAll('.msg.assistant .action-btn[data-action="regenerate"]');
  allRegenBtns.forEach(function(btn) {
    btn.remove();
  });
}

function stripHtmlForSpeech(html) {
  var tmp = document.createElement('div');
  tmp.innerHTML = html;
  return (tmp.textContent || tmp.innerText || '').trim();
}

// 清洗复制文本：去掉视频卡片 HTML 块和 bilibili 链接
function cleanTextForCopy(text) {
  if (!text) return '';
  // 去掉 <!--VIDEOS-->...<!--/VIDEOS--> 视频 HTML 块
  var cleaned = text.replace(/<!--VIDEOS-->[\s\S]*?<!--\/VIDEOS-->/g, '');
  // 去掉 bilibili 链接 [title](https://...bilibili...)
  cleaned = cleaned.replace(/\[([^\]]*)\]\(https?:\/\/[^)]*bilibili[^)]*\)/g, '');
  // 去掉视频卡片相关行（包含 video-card、video-thumb 之类的 HTML 片段）
  cleaned = cleaned.replace(/<div class="video-cards"[\s\S]*?<\/div>\s*<\/div>/g, '');
  // 清理多余空行
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
  return cleaned.trim();
}

function showCopyToast(msg) {
  var old = document.querySelector('.copy-toast');
  if (old) old.remove();
  var toast = document.createElement('div');
  toast.className = 'copy-toast';
  toast.textContent = msg || '已复制到剪贴板';
  document.body.appendChild(toast);
  setTimeout(function() { if (toast.parentNode) toast.remove(); }, 1800);
}

function toggleSpeech(mdText, btn) {
  // 如果当前按钮正在朗读 → 停止
  if (btn.classList.contains('speaking')) {
    window.speechSynthesis && window.speechSynthesis.cancel();
    btn.classList.remove('speaking');
    _speakingBtn = null;
    return;
  }

  // 停止其他正在播放的语音
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  if (_speakingBtn && _speakingBtn !== btn) {
    _speakingBtn.classList.remove('speaking');
  }

  var plainText = stripHtmlForSpeech(renderMD(mdText));
  if (!plainText) return;
  if (!window.speechSynthesis) { showCopyToast('浏览器不支持朗读功能'); return; }

  // 确保语音列表已加载
  if (!_sweetVoice) {
    var voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) _sweetVoice = pickSweetVoice(voices);
  }

  var utterance = new SpeechSynthesisUtterance(plainText);
  utterance.lang = 'zh-CN';
  utterance.rate = 0.95;    // 稍慢一点更清晰
  utterance.pitch = 1.25;   // 稍高音调 → 甜妹感
  if (_sweetVoice) utterance.voice = _sweetVoice;

  btn.classList.add('speaking');
  _speakingBtn = btn;

  utterance.onend = function() {
    btn.classList.remove('speaking');
    _speakingBtn = null;
  };
  utterance.onerror = function() {
    btn.classList.remove('speaking');
    _speakingBtn = null;
  };

  window.speechSynthesis.speak(utterance);
}

function toggleFeedback(btn, msgDiv, type) {
  var otherType = type === 'like' ? 'dislike' : 'like';
  var otherBtn = msgDiv.querySelector('[data-action="' + otherType + '"]');
  if (btn.classList.contains(type + 'd')) {
    btn.classList.remove(type + 'd');
  } else {
    btn.classList.add(type + 'd');
    if (otherBtn) otherBtn.classList.remove(otherType + 'd');
  }
}

function regenerateMessage(msgDiv, userQuery, workflowType) {
  if (isStreaming) return;
  msgDiv.style.opacity = '0';
  msgDiv.style.transform = 'translateY(-8px)';
  msgDiv.style.transition = 'all 0.2s ease';
  setTimeout(function() {
    msgDiv.remove();
    scrollDown();
    if (workflowType === 'vision') {
      sendDirectQuery('请重新分析刚才上传的图片');
    } else if (workflowType) {
      var wfBtn = document.querySelector('.topbar-btn[data-wf="' + workflowType + '"]');
      if (wfBtn) wfBtn.click();
    } else if (userQuery) {
      sendDirectQuery(userQuery);
    }
  }, 200);
}

// ====== 不喜欢反馈调查面板 ======
function showFeedbackSurvey(msgDiv) {
  // 关闭已有面板
  closeFeedbackSurvey(msgDiv);

  var survey = document.createElement('div');
  survey.className = 'feedback-survey';
  survey.innerHTML =
    '<div class="feedback-title">这条回复哪里不好？</div>' +
    '<div class="feedback-tags">' +
      '<span class="feedback-tag" data-reason="内容不准确">内容不准确</span>' +
      '<span class="feedback-tag" data-reason="回答不完整">回答不完整</span>' +
      '<span class="feedback-tag" data-reason="格式混乱">格式混乱</span>' +
      '<span class="feedback-tag" data-reason="无关内容">无关内容</span>' +
      '<span class="feedback-tag" data-reason="其他">其他</span>' +
    '</div>' +
    '<textarea class="feedback-input" placeholder="补充更多反馈（可选）" rows="2"></textarea>' +
    '<div class="feedback-actions">' +
      '<button class="feedback-submit">提交</button>' +
      '<button class="feedback-close">取消</button>' +
    '</div>';

  // 标签点击
  survey.querySelectorAll('.feedback-tag').forEach(function(tag) {
    tag.addEventListener('click', function() {
      survey.querySelectorAll('.feedback-tag').forEach(function(t) { t.classList.remove('selected'); });
      tag.classList.add('selected');
    });
  });

  // 提交
  survey.querySelector('.feedback-submit').addEventListener('click', function() {
    var selected = survey.querySelector('.feedback-tag.selected');
    var reason = selected ? selected.dataset.reason : '未选择';
    var detail = survey.querySelector('.feedback-input').value.trim();
    submitFeedback(msgDiv, reason, detail);
    closeFeedbackSurvey(msgDiv);
  });

  // 取消
  survey.querySelector('.feedback-close').addEventListener('click', function() {
    closeFeedbackSurvey(msgDiv);
    // 同时取消不喜欢状态
    var dislikeBtn = msgDiv.querySelector('[data-action="dislike"]');
    if (dislikeBtn) dislikeBtn.classList.remove('disliked');
  });

  msgDiv.appendChild(survey);
  // 入场动画：从下方滑出
  requestAnimationFrame(function() { survey.classList.add('show'); });
  scrollDown();
}

function closeFeedbackSurvey(msgDiv) {
  var existing = msgDiv.querySelector('.feedback-survey');
  if (existing) {
    existing.classList.remove('show');
    setTimeout(function() { if (existing.parentNode) existing.remove(); }, 260);
  }
}

function submitFeedback(msgDiv, reason, detail) {
  var originalText = msgDiv.dataset.originalText || '';
  var userQuery = msgDiv.dataset.userQuery || '';
  // 提交到后端 FeedbackRecord 表
  fetch(API + '/agent/feedback', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-ID': getUserId()
    },
    body: JSON.stringify({
      session_id: (window._userSessionId || 'sess_default'),
      user_message: userQuery.slice(0, 500),
      agent_response: originalText.slice(0, 2000),
      rating: 'negative',
      comment: (reason + (detail ? ' | ' + detail : '')).slice(0, 500)
    })
  }).catch(function(){});
  showCopyToast('感谢反馈，我们会持续改进');
}

function initActionButtons() {
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.action-btn');
    if (!btn) return;
    e.stopPropagation();
    var action = btn.dataset.action;
    var msgDiv = btn.closest('.msg.assistant');
    if (!msgDiv) return;
    var originalText = msgDiv.dataset.originalText || '';
    var userQuery = msgDiv.dataset.userQuery || '';
    var workflowType = msgDiv.dataset.workflowType || '';

    switch(action) {
      case 'copy':
        var copyText = cleanTextForCopy(originalText);
        navigator.clipboard.writeText(copyText).then(function() {
          showCopyToast('已复制到剪贴板');
        }).catch(function() {
          var ta = document.createElement('textarea');
          ta.value = copyText; ta.style.position = 'fixed'; ta.style.opacity = '0';
          document.body.appendChild(ta); ta.select(); document.execCommand('copy');
          document.body.removeChild(ta); showCopyToast('已复制到剪贴板');
        });
        break;
      case 'speak':
        toggleSpeech(originalText, btn);
        break;
      case 'like':
        toggleFeedback(btn, msgDiv, 'like');
        closeFeedbackSurvey(msgDiv);
        break;
      case 'dislike':
        toggleFeedback(btn, msgDiv, 'dislike');
        if (btn.classList.contains('disliked')) {
          showFeedbackSurvey(msgDiv);
        } else {
          closeFeedbackSurvey(msgDiv);
        }
        break;
      case 'regenerate':
        regenerateMessage(msgDiv, userQuery, workflowType);
        break;
    }
  });
}

// ========== Image Upload + Vision ==========
async function handleImageUpload(event) {
  var file = event.target.files[0];
  if (!file) return;
  if (isStreaming) { alert('Please wait for current reply'); return; }

  var msgs = document.querySelector('.messages-inner');

  // 1. 先插入用户图片（上方）
  var userDiv = document.createElement("div");
  userDiv.className = "msg user";
  var imgUrl = URL.createObjectURL(file);
  userDiv.innerHTML = '<div class="bubble" style="padding:8px"><img src="' + imgUrl + '" style="max-width:200px;max-height:200px;border-radius:8px;display:block;cursor:pointer" onclick="showLightbox(\'' + imgUrl + '\')"></div>';
  msgs.appendChild(userDiv);

  // 2. 再插入 AI 回复气泡（下方）
  var div = document.createElement('div');
  div.className = 'msg assistant';
  div.innerHTML = '<div class="avatar"><img src="/static/favicon.png" width="36" height="36" style="border-radius:50%;object-fit:cover"></div><div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>';
  msgs.appendChild(div);
  var bubble = div.querySelector('.bubble');
  scrollDown();

  var formData = new FormData();
  formData.append('file', file);
  formData.append('prompt', '请详细描述图片内容。如果是食材列出名称数量，如果是家电列型号状态，如果是文字逐字识读，如果是场景描述环境。');

  try {
    var resp = await fetch(API + '/agent/vision/analyze', { method: 'POST', body: formData });
    var data = await resp.json();
    if (data.status === 'error') {
      bubble.innerHTML = renderMD('Image analysis failed: ' + (data.error || 'Unknown error'));
      return;
    }
    var tw = typewriterStart(bubble, function(finalText) { addActionButtons(div, finalText, null, 'vision'); });
    tw.feed(data.agent_response || data.vision_description || 'Analysis complete');
    tw.flush();
  } catch(e) {
    bubble.innerHTML = 'Upload failed: ' + escapeHtml(e.message);
  }
  scrollDown();
  event.target.value = '';
}

// ========== 图片放大 ==========
function showLightbox(url) {
  var lb = document.createElement('div');
  lb.className = 'lightbox';
  lb.innerHTML = '<img src="' + url + '" style="max-width:90vw;max-height:90vh;border-radius:8px">';
  lb.onclick = function() { lb.remove(); };
  document.body.appendChild(lb);
}

// ========== 安全确认弹窗 ==========
function showConfirmationDialog(pendingCalls) {
  // 缓存待确认数据
  _pendingConfirmation = pendingCalls;
  // 填入详情
  var detailsEl = document.getElementById("confirmDetails");
  var msgEl = document.getElementById("confirmMessage");
  if (pendingCalls && pendingCalls.length > 0) {
    var call = pendingCalls[0];
    msgEl.textContent = call.message || "即将执行以下操作，请确认：";
    var html = "<strong>操作：</strong>" + escapeHtml(call.tool) + "<br>";
    if (call.args) {
      html += "<strong>参数：</strong>";
      for (var k in call.args) {
        if (k !== "user_id") {
          html += k + "=" + escapeHtml(String(call.args[k])) + " ";
        }
      }
    }
    detailsEl.innerHTML = html;
    // 多操作时显示数量
    if (pendingCalls.length > 1) {
      detailsEl.innerHTML += "<br><br>共 <strong>" + pendingCalls.length + "</strong> 个操作待确认";
    }
  } else {
    msgEl.textContent = "即将执行操作，请确认：";
    detailsEl.innerHTML = "暂无详细信息";
  }
  document.getElementById("confirmModal").style.display = "flex";
}

function cancelConfirmation() {
  document.getElementById("confirmModal").style.display = "none";
  _pendingConfirmation = null;
  // 移除 AI 的确认询问气泡
  var msgs = document.querySelectorAll(".msg.assistant");
  if (msgs.length > 0) {
    var last = msgs[msgs.length - 1];
    if (last.querySelector(".pending-confirm")) {
      last.remove();
    }
  }
}

async function approveConfirmation() {
  document.getElementById("confirmModal").style.display = "none";
  if (!_pendingConfirmation) return;

  var userQuery = "";
  // 从最后一条用户消息获取原始输入
  var userMsgs = document.querySelectorAll(".msg.user .bubble");
  if (userMsgs.length > 0) {
    userQuery = (userMsgs[userMsgs.length - 1].textContent || "").trim();
  }

  // 移除确认询问气泡
  cancelConfirmation();

  // 带着 confirmed_tools 重新发送请求
  if (!userQuery) {
    userQuery = "请继续执行";
  }

  var confirmedTools = _pendingConfirmation.map(function(c) {
    return { tool: c.tool, args: c.args };
  });
  _pendingConfirmation = null;

  // 构造带确认的请求
  isStreaming = true;
  if (activeAbort) { activeAbort.abort(); activeAbort = null; }
  typewriterCancel();

  var msgs = document.querySelector(".messages-inner");
  var div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = '<div class="avatar"><img src="/static/favicon.png" style="width:36px;height:36px;border-radius:50%;object-fit:cover"></div><div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>';
  msgs.appendChild(div);
  var streamEl = div.querySelector(".bubble");
  scrollDown();

  var tw = null;
  try {
    activeAbort = new AbortController();
    var body = {
      session_id: window._userSessionId || "sess_default",
      user_id: getUserId(),
      message: userQuery,
      intent: "general",
      stream: true,
      confirmed_tools: confirmedTools
    };
    var resp = await fetch(API + "/agent/chat/stream", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(body),
      signal: activeAbort.signal
    });
    if (!resp.ok) throw new Error("请求失败(" + resp.status + ")");
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";
    while (true) {
      var result = await reader.read();
      if (result.done) break;
      buffer += decoder.decode(result.value, { stream: true });
      var lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (!line.startsWith("data: ")) continue;
        try {
          var d = JSON.parse(line.slice(6));
          if (d.done) break;
          if (d.requires_confirmation) {
            // 又触发确认——递归显示
            setTimeout(function() {
              showConfirmationDialog(d.pending_dangerous_calls || []);
            }, 100);
            break;
          }
          if (d.video) { _pendingVideoHtml = d.video; continue; }
          if (d.content) {
            if (!tw) tw = typewriterStart(streamEl, function(finalText) {
              addActionButtons(div, finalText, userQuery);
            });
            tw.feed(d.content);
          }
        } catch(e) {}
      }
    }
    if (tw) {
      tw.flush();
    } else {
      // 确认后可能无文字输出（纯执行操作）
      streamEl.innerHTML = renderMD("✅ 操作已执行");
      addActionButtons(div, "✅ 操作已执行", userQuery);
    }
  } catch(err) {
    if (err.name === "AbortError") { typewriterCancel(); div.remove(); return; }
    typewriterCancel();
    streamEl.innerHTML = "网络异常: " + escapeHtml(err.message);
    addActionButtons(div, "", userQuery);
  }
  isStreaming = false;
  activeAbort = null;
  scrollDown();
}
