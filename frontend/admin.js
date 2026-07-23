const A = "/api/v1";
const U = "user_001";

async function i() {
    await Promise.all([ls(), lse(), lf(), lt2()]);
}

async function ls() {
    try {
        const [t, f] = await Promise.all([
            fetch(A + "/agent/tokens/stats/" + U + "?days=7").then(r => r.json()),
            fetch(A + "/agent/feedback/stats/" + U).then(r => r.json())
        ]);
        g("ttt").textContent = fn(t.total_tokens);
        g("ttc").textContent = "¥" + t.total_cost_cny.toFixed(2);
        g("tca").textContent = t.calls_count;
        g("tsf").textContent = f.satisfaction_rate + "%";
    } catch(e) {}
}

async function lse() {
    try {
        const r = await fetch(A + "/agent/trace/recent/" + U + "?limit=20");
        const d = await r.json();
        const s = g("ses");
        (d.recent_sessions || []).forEach(x => {
            const o = document.createElement("option");
            o.value = x.session_id;
            o.textContent = new Date(x.started_at).toLocaleString("zh-CN") + " | " + (x.user_message || "").substring(0, 40);
            s.appendChild(o);
        });
    } catch(e) {}
}

async function lt(sid) {
    if (!sid) return;
    try {
        const r = await fetch(A + "/agent/trace/" + sid);
        const d = await r.json();
        const el = g("trd");
        if (!d.steps || !d.steps.length) { el.innerHTML = "<p class='eh'>暂无追踪数据</p>"; return; }
        let h = "<div style='font-size:12px;color:#8F97B0;margin-bottom:8px'>" + d.total_steps + " 步 | 总耗时 " + d.total_duration_ms + "ms</div>";
        d.steps.forEach(s => {
            const c = s.step_type === "llm_call" ? "l" : s.step_type === "tool_result" ? "t" : s.step_type === "error" ? "e" : "f";
            const lb = s.step_type === "llm_call" ? "推理" : s.step_type === "tool_result" ? (s.detail.tool || "工具") : s.step_type === "error" ? "异常" : "完成";
            const det = s.detail.tool_calls_planned ? s.detail.tool_calls_planned.map(t => t.name).join(", ") : ((s.detail.result_summary || s.detail.response || "").substring(0, 120));
            h += "<div class='tr'><span class='tt " + c + "'>" + lb + "</span><span class='td'>" + eh(det) + "</span><span class='tm'>" + (s.duration_ms || 0) + "ms</span></div>";
        });
        el.innerHTML = h;
    } catch(e) {}
}

async function lf() {
    try {
        const r = await fetch(A + "/agent/feedback/stats/" + U);
        const d = await r.json();
        const el = g("fbs");
        if (!d.recent || !d.recent.length) { el.innerHTML = "<p class='eh'>暂无反馈记录</p>"; return; }
        let h = "<table><thead><tr><th>时间</th><th>用户消息</th><th>AI回复</th><th>评价</th></tr></thead><tbody>";
        d.recent.forEach(f => {
            const ic = f.rating === "positive" ? "👍" : f.rating === "negative" ? "👎" : "➖";
            h += "<tr><td>" + new Date(f.created_at).toLocaleString("zh-CN") + "</td><td>" + eh(f.user_message.substring(0, 40)) + "</td><td>" + eh(f.agent_response.substring(0, 50)) + "</td><td>" + ic + " " + f.rating + "</td></tr>";
        });
        h += "</tbody></table>";
        el.innerHTML = h;
    } catch(e) {}
}

async function lt2() {
    try {
        const r = await fetch(A + "/agent/tokens/daily/" + U + "?days=7");
        const d = await r.json();
        const el = g("trs");
        if (!d.daily || !d.daily.length) { el.innerHTML = "<p class='eh'>暂无数据</p>"; return; }
        const mx = Math.max(...d.daily.map(x => x.tokens), 1);
        let h = "<div style='display:flex;align-items:flex-end;gap:12px;height:120px;padding:0 4px'>";
        d.daily.reverse().forEach(x => {
            const pct = Math.max(x.tokens / mx * 100, 4);
            h += "<div style='flex:1;text-align:center'><div style='background:#5B6ABF;height:" + pct + "%;border-radius:4px 4px 0 0;min-height:4px' title='" + x.tokens + " tokens'></div><div style='font-size:10px;color:#8F97B0;margin-top:4px'>" + x.date.slice(5) + "</div><div style='font-size:11px;font-weight:600'>" + fn(x.tokens) + "</div></div>";
        });
        h += "</div>";
        el.innerHTML = h;
    } catch(e) {}
}

function fn(n) { if (n >= 1e6) return (n/1e6).toFixed(1)+"M"; if (n >= 1e3) return (n/1e3).toFixed(1)+"K"; return String(n); }
function eh(s) { var d = document.createElement("div"); d.textContent = s || ""; return d.innerHTML; }
function g(id) { return document.getElementById(id); }

document.addEventListener("DOMContentLoaded", i);
