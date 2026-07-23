const API = "/api/v1";
const USER = "user_001";

const AGENTS = {
  default: {
    name: "家务AI管家", icon: "🏠",
    desc: "购物·膳食·家电·维保·安防·事务 — 一个管家全搞定",
    chipGroups: [
      { label: "饮食料理", chips: ["看看冰箱里有什么","帮我规划一周菜谱","冰箱食材快过期了能做什么","帮我生成购物清单并比价"] },
      { label: "家居安防维保", chips: ["预约今晚错峰运行","检查家电维保状态","查看门口监控","今天有什么待办"] }
    ],
    placeholder: "需要我做什么？购物、菜谱、家电、安防...都可以",
    intent: "general", color: "primary"
  }
};

let isStreaming = false, activeAbort = null;

document.addEventListener("DOMContentLoaded", () => {
  updateGreeting();
  renderChips();
  initWorkflowBtns();
  initChipDelegation();
  updateStatusBar();
  setInterval(updateStatusBar, 30000);
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
      var msgs = document.querySelector('.messages-inner');
      var div = document.createElement("div");
      div.className = "msg assistant";
      div.innerHTML = '<div class="avatar">🏠</div><div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>';
      msgs.appendChild(div);
      scrollDown();
      try {
        var resp = await fetch(API + "/agent/workflow/" + type + "?user_id=" + USER + "&session_id=wf_" + Date.now(), { method: "POST" });
        var data = await resp.json();
        var text = (data.results && data.results.response) || data.response || "";
        div.querySelector(".bubble").innerHTML = renderMD(text || "完成");
      } catch(e) {
        div.querySelector(".bubble").innerHTML = "执行失败: " + escapeHtml(e.message);
      }
      this.disabled = false;
      this.textContent = origText;
      scrollDown();
    });
  });
}

async function updateStatusBar() {
  try {
    var [devices, alerts] = await Promise.all([
      fetch(API + "/appliance/status/" + USER).then(function(r) { return r.json(); }),
      fetch(API + "/dashboard/alerts").then(function(r) { return r.json(); })
    ]);
    var devCount = devices.appliances ? devices.appliances.length : 0;
    document.getElementById("statDevicesText").textContent = "已接入 " + devCount + " 台设备";
    if (devices.appliances && devices.appliances.length > 0) {
      document.getElementById("statDevices").title = devices.appliances.map(function(a) { return a.name; }).join("、");
      document.getElementById("statDevices").onclick = function() {
        document.getElementById("userInput").value = "查看所有家电状态";
        sendMessage();
      };
    }
    var taskCount = alerts.count || 0;
    document.getElementById("statTasksText").textContent = "待办 " + taskCount + " 项";
    document.getElementById("statTasks").title = alerts.alerts && alerts.alerts.length ? alerts.alerts.join("\n") : "暂无待办";
  } catch(e) {}
}

async function sendMessage() {
  var input = document.getElementById("userInput");
  var text = input.value.trim();
  if (!text || isStreaming) return;
  input.value = ""; input.focus(); isStreaming = true;
  if (activeAbort) { activeAbort.abort(); activeAbort = null; }
  var msgs = document.querySelector('.messages-inner');
  msgs.innerHTML += '<div class="msg user"><div class="avatar">👤</div><div class="bubble">' + escapeHtml(text) + '</div>';
  var div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = '<div class="avatar">🏠</div><div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>';
  msgs.appendChild(div);
  var streamEl = div.querySelector(".bubble");
  scrollDown();
  var btn = document.getElementById("sendBtn");
  if (btn) btn.disabled = true;
  try {
    activeAbort = new AbortController();
    var resp = await fetch(API + "/agent/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: "sess_default", user_id: USER, message: text, intent: "general", stream: true }),
      signal: activeAbort.signal
    });
    if (!resp.ok) throw new Error("请求失败(" + resp.status + ")");
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var fullText = "", buffer = "";
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
          if (d.content) { fullText += d.content; streamEl.innerHTML = renderMD(fullText); }
        } catch(e) {}
      }
      scrollDown();
    }
    streamEl.innerHTML = renderMD(fullText || "(空)");
  } catch(err) {
    if (err.name === "AbortError") { div.remove(); return; }
    streamEl.innerHTML = "网络异常: " + escapeHtml(err.message);
  }
  if (btn) btn.disabled = false;
  isStreaming = false;
  activeAbort = null;
  scrollDown();
}

function scrollDown() {
  var m = document.getElementById("messages");
  if (m) setTimeout(function() { m.scrollTop = m.scrollHeight; }, 50);
}

function escapeHtml(t) {
  var d = document.createElement("div");
  d.textContent = t || "";
  return d.innerHTML;
}

function renderMD(t) {
  if (!t) return "";
  var h = t;
  h = h.replace(/```(\w*)\n([\s\S]*?)```/g, function(_,l,c) { return '<pre><code>' + escapeHtml(c.trim()) + '</code></pre>'; });
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  h = h.replace(/^---$/gm, '<hr>');
  // Markdown tables
  h = h.replace(/(\|.+\|\n\|[-| :]+\|\n((?:\|.+\|\n?)*))/gm, function(m) {
    var lines = m.trim().split('\n');
    if (lines.length < 2) return m;
    var t = '<table><thead><tr>';
    lines[0].split('|').filter(function(c) { return c.trim(); }).forEach(function(c) { t += '<th>' + c.trim() + '</th>'; });
    t += '</tr></thead><tbody>';
    for (var i = 2; i < lines.length; i++) {
      var cells = lines[i].split('|').filter(function(c) { return c.trim(); });
      if (cells.length) { t += '<tr>' + cells.map(function(c) { return '<td>' + c.trim() + '</td>'; }).join('') + '</tr>'; }
    }
    t += '</tbody></table>';
    return t;
  });
  // 提取视频卡片 HTML（用注释标记包裹，不受内部嵌套 div 影响）
  var videoHtml = '';
  h = h.replace(/<!--VIDEOS-->([\s\S]*?)<!--\/VIDEOS-->/g, function(_, m) {
    videoHtml += m; return '';
  });
  h = h.replace(/\n\n/g, '</p><p>');
  h = h.replace(/\n/g, '<br>');
  if (!h.startsWith('<')) h = '<p>' + h + '</p>';
  h = h.replace(/<p>\s*<\/p>/g, '');
  // 视频卡片追加到末尾，确保 <a> 可点击且不受 <p> 嵌套干扰
  return h + videoHtml;
}
