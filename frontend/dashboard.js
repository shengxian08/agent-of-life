/* ============================================================
   工作台 Dashboard — 自动化工作流管理
   ============================================================ */
const API = '/api/v1';
const USER = 'user_001';

const WF_NAMES = {
    daily: '每日家庭巡检', weekly: '每周膳食规划',
    evening: '晚间自动化', smart: '智能主动检测',
    security: '安防巡检'
};
const WF_ICONS = {
    daily: '🔍', weekly: '📅', evening: '🌙', smart: '🤖',
    security: '🛡️'
};

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    setInterval(loadDashboard, 30000); // 每30秒刷新
});

async function loadDashboard() {
    try {
        const [statusResp, historyResp] = await Promise.all([
            fetch(`${API}/dashboard/status`),
            fetch(`${API}/dashboard/history?limit=10`)
        ]);
        const status = await statusResp.json();
        const history = await historyResp.json();

        // 统计数字
        document.getElementById('alertCount').textContent = status.alerts_count || 0;
        document.getElementById('completedCount').textContent =
            (history.results || []).filter(r => r.status === 'completed').length;
        if (history.results && history.results.length > 0) {
            const last = history.results[0];
            const t = new Date(last.finished_at || last.started_at);
            document.getElementById('lastRunTime').textContent =
                t.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }

        // 执行历史
        renderHistory(history.results || []);
    } catch (e) {
        console.error('Dashboard load failed:', e);
    }
}

function renderHistory(results) {
    const list = document.getElementById('historyList');
    if (!results || results.length === 0) {
        list.innerHTML = '<div class="empty-state">📭 还没有执行记录，点击上方工作流卡片开始</div>';
        return;
    }

    list.innerHTML = results.map((r, i) => {
        const time = new Date(r.finished_at || r.started_at);
        const timeStr = time.toLocaleString('zh-CN', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
        const statusClass = r.status === 'completed' ? 'completed' :
                           r.status === 'running' ? 'running' : 'failed';
        const icon = r.status === 'completed' ? '✅' :
                    r.status === 'running' ? '⏳' : '❌';
        const wfId = r.workflow_id;

        return `
            <div class="history-item ${statusClass}" id="item-${wfId}">
                <div class="history-icon">${icon}</div>
                <div class="history-body" onclick="toggleDetail('${wfId}')">
                    <h4>${r.workflow_name || '工作流'}
                        <span class="expand-hint">点击查看详情 ▾</span>
                    </h4>
                    <div class="history-summary">${escapeHtml(r.summary || '')}</div>
                    ${r.alerts && r.alerts.length ? `
                        <div class="history-alerts">
                            ${r.alerts.map(a => `<span class="history-alert-tag">${escapeHtml(a)}</span>`).join('')}
                        </div>` : ''}
                    <div class="history-meta">${r.steps_count || 0} 个步骤 · 点击展开</div>
                </div>
                <div class="history-time">${timeStr}</div>
                <div class="history-detail" id="detail-${wfId}" style="display:none"></div>
            </div>`;
    }).join('');
}

// ---- 展开/收起工作流详情 ----
async function toggleDetail(wfId) {
    const detailDiv = document.getElementById('detail-' + wfId);
    const itemDiv = document.getElementById('item-' + wfId);

    // 如果已经展开，收起
    if (detailDiv.style.display === 'block') {
        detailDiv.style.display = 'none';
        itemDiv.classList.remove('expanded');
        return;
    }

    // 如果已加载过数据，直接显示
    if (detailDiv.innerHTML) {
        detailDiv.style.display = 'block';
        itemDiv.classList.add('expanded');
        return;
    }

    // 首次展开：加载详情
    detailDiv.innerHTML = '<div class="detail-loading"><span class="spinner"></span> 加载详情...</div>';
    detailDiv.style.display = 'block';
    itemDiv.classList.add('expanded');

    try {
        const resp = await fetch(`${API}/dashboard/history/${wfId}`);
        const data = await resp.json();

        if (data.steps && data.steps.length > 0) {
            detailDiv.innerHTML = `
                <div class="detail-header">📋 执行步骤详情</div>
                ${data.steps.map((s, i) => {
                    const actions = getStepActions(s, data.workflow_name);
                    return `
                    <div class="detail-step">
                        <div class="detail-step-header">
                            <span class="step-num">步骤 ${i+1}</span>
                            <span class="step-agent">${s.agent || 'AI'}</span>
                            <span class="step-msg">${escapeHtml(s.message || '')}</span>
                        </div>
                        <div class="step-response">${simpleMarkdown(s.response || '')}</div>
                        ${actions.length ? `
                            <div class="step-actions">
                                ${actions.map(a => `
                                    <button class="action-btn" data-agent="${a.agent}" data-msg="${escapeHtml(a.msg)}">
                                        ${a.icon} ${a.label}
                                    </button>
                                `).join('')}
                            </div>` : ''}
                    </div>`;
                }).join('')}
            `;
        } else {
            detailDiv.innerHTML = '<div class="detail-loading">暂无详细步骤数据</div>';
        }
    } catch (err) {
        detailDiv.innerHTML = '<div class="detail-loading">加载失败：' + escapeHtml(err.message) + '</div>';
    }
}

// ---- 智能生成行动按钮（返回 data 属性，由事件委托处理）----
function getStepActions(step, workflowName) {
    const actions = [];
    const agent = step.agent || '';
    const resp = (step.response || '').toLowerCase();

    if (agent.includes('shopping') || resp.includes('过期') || resp.includes('库存') || resp.includes('冰箱')) {
        actions.push({
            icon: '🛒', label: '去生成购物清单',
            agent: 'shopping', msg: '根据刚才的冰箱检查结果，帮我生成购物清单'
        });
    }
    if (agent.includes('meal') || resp.includes('菜') || resp.includes('食谱') || resp.includes('过期')) {
        actions.push({
            icon: '🍳', label: '去规划今天菜谱',
            agent: 'meal', msg: '冰箱里有临期食材，帮我规划今天吃什么，优先用快过期的'
        });
    }
    if (agent.includes('appliance') || resp.includes('错峰') || resp.includes('预约')) {
        actions.push({
            icon: '⚡', label: '去预约家电运行',
            agent: 'appliance', msg: '帮我预约今晚错峰运行'
        });
    }
    if (agent.includes('maintenance') || resp.includes('账单') || resp.includes('缴费')) {
        actions.push({
            icon: '📋', label: '去处理账单',
            agent: 'maintenance', msg: '帮我查看待缴费账单并处理'
        });
    }
    if (agent.includes('maintenance') || resp.includes('维保') || resp.includes('保养')) {
        actions.push({
            icon: '🔧', label: '去预约维保',
            agent: 'maintenance', msg: '帮我查看需要保养的家电并预约维修'
        });
    }
    return actions;
}

// ---- 跳转到对话页（全局函数，URL 参数传递）----
function goToChat(agent, msg) {
    const params = new URLSearchParams();
    params.set('agent', agent);
    params.set('msg', msg);
    window.location.href = '/app?' + params.toString();
}

// ---- 事件委托：处理所有 action-btn 点击 ----
document.addEventListener('click', function(e) {
    const btn = e.target.closest('.action-btn');
    if (!btn) return;
    const agent = btn.getAttribute('data-agent');
    const msg = btn.getAttribute('data-msg');
    if (agent && msg) {
        goToChat(agent, msg);
    }
});

// 简单的 Markdown 渲染
function simpleMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    return '<p>' + html + '</p>';
}

// ---- 触发工作流 ----
async function runWorkflow(type) {
    const cards = document.querySelectorAll('.wf-card');
    cards.forEach(c => c.classList.remove('running'));

    // 找到被点击的卡片并标记
    const clicked = document.querySelector(`.wf-card[onclick="runWorkflow('${type}')"]`);
    if (clicked) clicked.classList.add('running');

    try {
        const resp = await fetch(`${API}/dashboard/run/${type}?user_id=${USER}`, { method: 'POST' });
        const data = await resp.json();
        clicked.classList.remove('running');
        // 刷新仪表盘
        await loadDashboard();
    } catch (err) {
        if (clicked) clicked.classList.remove('running');
        alert('工作流执行失败：' + err.message);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
