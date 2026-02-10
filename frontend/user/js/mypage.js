/**
 * ダッシュボード (マイページ)
 */

// --- 初期化 ---
async function loadDashboard() {
    const didCheckout = await handleCheckoutComplete();
    loadGreeting();
    await loadPlanCards();
    // checkout直後に購読が空ならポーリングで待機
    if (didCheckout && _subs.length === 0) {
        await pollForSubscription();
    }
    loadAnswersCard();
    loadHistoryCard();
}

// --- Checkout完了処理 ---
async function handleCheckoutComplete() {
    const params = new URLSearchParams(location.search);
    const sessionId = params.get('session_id');
    if (!sessionId) return false;

    // checkout-completeを呼んで購読レコード作成を試みる
    for (let i = 0; i < 3; i++) {
        try {
            await API.post('/api/checkout-complete', { session_id: sessionId });
            break;
        } catch {
            // リトライ (Webhook処理済みの場合も含む)
            if (i < 2) await new Promise(r => setTimeout(r, 1000));
        }
    }

    // URLクリーンアップ (session_idを除去)
    params.delete('session_id');
    const clean = params.toString();
    const newUrl = location.pathname + (clean ? '?' + clean : '');
    history.replaceState(null, '', newUrl);
    return true;
}

// --- Webhook待ちポーリング ---
async function pollForSubscription() {
    const el = document.getElementById('plan-cards');
    el.innerHTML = `
        <div class="dash-card">
            <div class="empty-state">
                <p>購読情報を確認中...</p>
            </div>
        </div>`;

    for (let i = 0; i < 10; i++) {
        await new Promise(r => setTimeout(r, 2000));
        try {
            _subs = await API.get('/api/my-subscriptions');
            if (_subs.length > 0) {
                el.innerHTML = _subs.map(s => renderPlanCard(s)).join('');
                return;
            }
        } catch { break; }
    }
    // タイムアウト: 通常表示にフォールバック
    el.innerHTML = `
        <div class="dash-card">
            <div class="empty-state">
                <p>購読の反映に時間がかかっています。ページを再読み込みしてください。</p>
                <button class="d-btn d-btn-secondary d-btn-sm" onclick="location.reload()">再読み込み</button>
            </div>
        </div>`;
}

// --- ユーティリティ ---
function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

function fmtDate(iso) {
    if (!iso) return '-';
    return new Date(iso).toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric' });
}

function fmtPrice(yen) {
    if (yen == null) return '-';
    if (yen === 0) return '無料';
    return '¥' + yen.toLocaleString() + '/月';
}

function statusBadge(status, cancelEnd) {
    if (cancelEnd) return '<span class="plan-badge badge-cancel">解約予約済</span>';
    const map = {
        active:   ['badge-active', '有効'],
        trialing: ['badge-trialing', 'トライアル中'],
        past_due: ['badge-pastdue', '支払い遅延'],
        canceled: ['badge-cancel', '解約済'],
        admin_added: ['badge-admin', '管理者追加'],
    };
    const [cls, label] = map[status] || ['badge-cancel', status];
    return `<span class="plan-badge ${cls}">${label}</span>`;
}

// --- グリーティング ---
async function loadGreeting() {
    try {
        const p = await API.get('/api/me/profile');
        const name = ((p.name_last || '') + ' ' + (p.name_first || '')).trim() || 'ユーザー';
        document.getElementById('dash-greeting').textContent = name + ' さん';
    } catch {
        document.getElementById('dash-greeting').textContent = 'ダッシュボード';
    }
}

// --- プランカード ---
let _subs = [];
async function loadPlanCards() {
    const el = document.getElementById('plan-cards');
    try {
        _subs = await API.get('/api/my-subscriptions');
        if (_subs.length === 0) {
            el.innerHTML = `
                <div class="dash-card">
                    <div class="empty-state">
                        <p>加入中のプランはありません</p>
                        <a href="/index.html">プランを探す</a>
                    </div>
                </div>`;
            return;
        }
        el.innerHTML = _subs.map(s => renderPlanCard(s)).join('');
    } catch (e) {
        el.innerHTML = `<div class="dash-card"><p style="color:#c00;">${esc(e.message)}</p></div>`;
    }
}

function renderPlanCard(s) {
    // admin_added はStripe連携なし・期間なしのため解約ボタンを表示しない
    const isAdminAdded = s.status === 'admin_added';
    const isActive = ['active', 'trialing', 'past_due'].includes(s.status) && !s.cancel_at_period_end;
    const showCancel = isActive && !isAdminAdded;
    const isPastDue = s.status === 'past_due';

    // ダウングレード予約表示
    let scheduledHtml = '';
    if (s.scheduled_plan_name) {
        scheduledHtml = `
        <div class="meta-item" style="border-top:1px solid #eee;padding-top:8px;margin-top:4px;">
            <div class="meta-label">プラン変更予定</div>
            <div class="meta-value">${esc(s.scheduled_plan_name)} (${fmtDate(s.scheduled_change_at)}〜)</div>
        </div>`;
    }

    // past_due 警告メッセージ
    let pastDueHtml = '';
    if (isPastDue) {
        pastDueHtml = `
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:10px 14px;margin-top:8px;font-size:13px;color:#856404;">
            お支払いが確認できていません。配信が一時停止されています。<br>
            <a href="javascript:void(0)" onclick="openBillingPortal()" style="color:#0056b3;">お支払い情報を更新する</a>
        </div>`;
    }

    return `
    <div class="dash-card">
        <div class="dash-card-title">加入中プラン</div>
        <div class="plan-header">
            <span class="plan-name">${esc(s.plan_name || 'プラン')}</span>
            ${statusBadge(s.status, s.cancel_at_period_end)}
        </div>
        <div class="plan-meta">
            ${!isAdminAdded ? `
            <div class="meta-item">
                <div class="meta-label">次回請求日</div>
                <div class="meta-value">${fmtDate(s.current_period_end)}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">請求金額</div>
                <div class="meta-value">${fmtPrice(s.plan_price)}</div>
            </div>` : ''}
            ${s.trial_end ? `
            <div class="meta-item">
                <div class="meta-label">トライアル終了日</div>
                <div class="meta-value">${fmtDate(s.trial_end)}</div>
            </div>` : ''}
            ${scheduledHtml}
        </div>
        ${pastDueHtml}
        ${showCancel ? `
        <div class="plan-actions">
            <button class="d-btn d-btn-secondary d-btn-sm" onclick="showPlanChangeModal()">プラン変更</button>
            <button class="d-btn d-btn-ghost d-btn-sm" onclick="cancelSub(${s.id})">解約する</button>
        </div>` : ''}
    </div>`;
}

function showPlanChangeModal() {
    // モーダルが既にあれば削除
    const existing = document.getElementById('plan-change-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'plan-change-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:1000;';
    modal.innerHTML = `
        <div style="background:#fff;padding:24px;border-radius:12px;max-width:400px;width:90%;text-align:center;">
            <p style="margin:0 0 20px;font-size:15px;line-height:1.6;">プランを変更するには次の画面で<br>「<strong>サブスクリプションを更新</strong>」をタップしてください。</p>
            <div style="display:flex;gap:12px;justify-content:center;">
                <button class="d-btn d-btn-ghost d-btn-sm" onclick="closePlanChangeModal()">キャンセル</button>
                <button class="d-btn d-btn-primary d-btn-sm" onclick="goToBillingPortal()">遷移する</button>
            </div>
        </div>
    `;
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closePlanChangeModal();
    });
    document.body.appendChild(modal);
}

function closePlanChangeModal() {
    const modal = document.getElementById('plan-change-modal');
    if (modal) modal.remove();
}

function goToBillingPortal() {
    closePlanChangeModal();
    openBillingPortal();
}

async function cancelSub(subId) {
    if (!confirm('この購読を解約しますか？\n期間終了まで引き続きご利用いただけます。')) return;
    try {
        await API.post(`/api/cancel-subscription/${subId}`);
        await loadPlanCards();
    } catch (e) {
        alert(e.message);
    }
}

// --- 回答情報 ---
async function loadAnswersCard() {
    const el = document.getElementById('answers-card');
    try {
        const subs = _subs.length ? _subs : await API.get('/api/my-subscriptions');
        if (subs.length === 0) { el.innerHTML = ''; return; }

        let html = '';
        for (const sub of subs) {
            try {
                const questions = await API.get(`/api/me/answers/${sub.plan_id}`);
                if (questions.length === 0) continue;

                const answersReadonly = questions.map(q => {
                    let val = q.answer || '';
                    if ((q.question_type === 'checkbox' || q.question_type === 'array') && val) {
                        try { val = JSON.parse(val).join(', '); } catch {}
                    }
                    return `
                        <div class="answer-row">
                            <span class="answer-label">${esc(q.label)}</span>
                            <span class="answer-value">
                                ${val ? esc(val) : '<span style="color:#ccc;">未回答</span>'}
                                ${q.carried_over ? ' <span class="answer-carried">(引き継ぎ)</span>' : ''}
                            </span>
                        </div>`;
                }).join('');

                const editForm = questions.map(q => renderAnswerEdit(q, sub.plan_id)).join('');

                html += `
                <div class="dash-card">
                    <div class="dash-card-title">回答情報</div>
                    <div class="answers-plan-title">${esc(sub.plan_name || 'プラン')}</div>
                    <div id="answers-readonly-${sub.plan_id}">${answersReadonly}</div>
                    <div class="edit-form" id="edit-form-${sub.plan_id}">
                        ${editForm}
                        <div style="margin-top:8px;">
                            <button class="d-btn d-btn-primary d-btn-sm" onclick="saveAnswers(${sub.plan_id})">保存</button>
                            <button class="d-btn d-btn-ghost d-btn-sm" onclick="toggleEdit(${sub.plan_id})">キャンセル</button>
                            <span id="answers-msg-${sub.plan_id}" class="d-msg"></span>
                        </div>
                    </div>
                    <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;">
                        <button class="d-btn d-btn-secondary d-btn-sm" onclick="toggleEdit(${sub.plan_id})">変更する</button>
                        <button class="d-btn d-btn-ghost d-btn-sm" onclick="toggleHistory(${sub.plan_id})">変更履歴</button>
                    </div>
                    <div id="history-${sub.plan_id}" style="display:none;margin-top:12px;"></div>
                </div>`;
            } catch {
                // 質問がないプランはスキップ
            }
        }

        el.innerHTML = html;
    } catch (e) {
        el.innerHTML = `<div class="dash-card"><p style="color:#c00;">${esc(e.message)}</p></div>`;
    }
}

function renderAnswerEdit(q, planId) {
    const val = esc(q.answer || '');
    let input = '';

    switch (q.question_type) {
        case 'textarea':
            input = `<textarea class="q-edit" data-qid="${q.question_id}" data-plan="${planId}">${val}</textarea>`;
            break;
        case 'number':
            input = `<input class="q-edit" data-qid="${q.question_id}" data-plan="${planId}" type="number" value="${val}">`;
            break;
        case 'date':
            input = `<input class="q-edit" data-qid="${q.question_id}" data-plan="${planId}" type="date" value="${val}">`;
            break;
        case 'select':
            input = `<select class="q-edit" data-qid="${q.question_id}" data-plan="${planId}">
                <option value="">選択してください</option>
                ${(q.options || []).map(o => `<option value="${esc(o)}" ${q.answer === o ? 'selected' : ''}>${esc(o)}</option>`).join('')}
            </select>`;
            break;
        case 'radio':
            input = (q.options || []).map(o => `
                <label class="choice-label">
                    <input type="radio" name="qe-${q.question_id}" class="q-edit-radio" data-qid="${q.question_id}" data-plan="${planId}" value="${esc(o)}" ${q.answer === o ? 'checked' : ''}> ${esc(o)}
                </label>
            `).join('');
            break;
        case 'checkbox': {
            let checked = [];
            try { checked = JSON.parse(q.answer || '[]'); } catch {}
            input = (q.options || []).map(o => `
                <label class="choice-label">
                    <input type="checkbox" class="q-edit-check" data-qid="${q.question_id}" data-plan="${planId}" value="${esc(o)}" ${checked.includes(o) ? 'checked' : ''}> ${esc(o)}
                </label>
            `).join('');
            break;
        }
        case 'array': {
            let vals = [];
            try { vals = JSON.parse(q.answer || '[]'); } catch {}
            if (vals.length === 0) vals = [''];
            const maxItems = q.array_max || 0;
            const minReq = q.array_min || 0;
            const hints = [];
            if (minReq >= 1) hints.push(minReq + '件以上必須');
            if (maxItems > 0) hints.push('最大' + maxItems + '件');
            const hintHtml = hints.length ? '<small style="color:#888;display:block;margin-top:4px;">' + hints.join(' / ') + '</small>' : '';
            const showRemove = vals.length > 1;
            const items = vals.map(v => `
                <div class="q-array-item" style="display:flex;gap:8px;margin-bottom:6px;">
                    <input type="text" class="q-array-input" data-qid="${q.question_id}" data-plan="${planId}" style="flex:1;" value="${esc(v)}">
                    ${showRemove ? `<button type="button" onclick="removeArrayItemEdit(this)" style="background:#f44;color:#fff;border:none;border-radius:4px;padding:0 10px;cursor:pointer;font-size:16px;">×</button>` : ''}
                </div>
            `).join('');
            input = `
                <div class="q-array-edit" data-qid="${q.question_id}" data-plan="${planId}" data-max="${maxItems}" data-min="${minReq}">
                    <div class="q-array-items">${items}</div>
                    <button type="button" onclick="addArrayItemEdit(this.closest('.q-array-edit'))" style="background:#f5f5f5;border:1px solid #ddd;border-radius:4px;padding:4px 14px;cursor:pointer;font-size:13px;">+ 追加</button>
                    ${hintHtml}
                </div>
            `;
            break;
        }
        default:
            input = `<input class="q-edit" data-qid="${q.question_id}" data-plan="${planId}" type="text" value="${val}">`;
    }

    return `<div class="form-group"><label>${esc(q.label)}${q.is_required ? ' *' : ''}</label>${input}</div>`;
}

function addArrayItemEdit(container) {
    const max = parseInt(container.dataset.max) || 0;
    const qid = container.dataset.qid;
    const planId = container.dataset.plan;
    const items = container.querySelectorAll('.q-array-item');
    if (max > 0 && items.length >= max) {
        alert('最大' + max + '件までです');
        return;
    }
    if (items.length === 1 && !items[0].querySelector('button')) {
        items[0].insertAdjacentHTML('beforeend', `<button type="button" onclick="removeArrayItemEdit(this)" style="background:#f44;color:#fff;border:none;border-radius:4px;padding:0 10px;cursor:pointer;font-size:16px;">×</button>`);
    }
    const div = document.createElement('div');
    div.className = 'q-array-item';
    div.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;';
    div.innerHTML = `<input type="text" class="q-array-input" data-qid="${qid}" data-plan="${planId}" style="flex:1;"><button type="button" onclick="removeArrayItemEdit(this)" style="background:#f44;color:#fff;border:none;border-radius:4px;padding:0 10px;cursor:pointer;font-size:16px;">×</button>`;
    container.querySelector('.q-array-items').appendChild(div);
}

function removeArrayItemEdit(btn) {
    const container = btn.closest('.q-array-edit');
    const items = container.querySelectorAll('.q-array-item');
    if (items.length <= 1) return;
    btn.closest('.q-array-item').remove();
    const remaining = container.querySelectorAll('.q-array-item');
    if (remaining.length === 1) {
        const rmBtn = remaining[0].querySelector('button');
        if (rmBtn) rmBtn.remove();
    }
}

function toggleEdit(planId) {
    const form = document.getElementById(`edit-form-${planId}`);
    form.classList.toggle('open');
}

async function saveAnswers(planId) {
    const answers = [];
    document.querySelectorAll(`.q-edit[data-plan="${planId}"]`).forEach(el => {
        answers.push({ question_id: parseInt(el.dataset.qid), answer: el.value });
    });
    document.querySelectorAll(`.q-edit-radio[data-plan="${planId}"]:checked`).forEach(el => {
        answers.push({ question_id: parseInt(el.dataset.qid), answer: el.value });
    });
    const checkMap = {};
    document.querySelectorAll(`.q-edit-check[data-plan="${planId}"]:checked`).forEach(el => {
        const qid = el.dataset.qid;
        if (!checkMap[qid]) checkMap[qid] = [];
        checkMap[qid].push(el.value);
    });
    Object.entries(checkMap).forEach(([qid, vals]) => {
        answers.push({ question_id: parseInt(qid), answer: JSON.stringify(vals) });
    });
    document.querySelectorAll(`.q-array-edit[data-plan="${planId}"]`).forEach(container => {
        const qid = container.dataset.qid;
        const vals = [];
        container.querySelectorAll('.q-array-input').forEach(input => {
            if (input.value.trim()) vals.push(input.value.trim());
        });
        answers.push({ question_id: parseInt(qid), answer: JSON.stringify(vals) });
    });

    try {
        await API.post(`/api/me/answers/${planId}`, answers);
        const msg = document.getElementById(`answers-msg-${planId}`);
        msg.textContent = '保存しました';
        setTimeout(() => msg.textContent = '', 3000);
        await loadAnswersCard();
    } catch (e) {
        alert(e.message);
    }
}

async function toggleHistory(planId) {
    const el = document.getElementById(`history-${planId}`);
    if (el.style.display !== 'none') {
        el.style.display = 'none';
        return;
    }
    el.innerHTML = '<p style="color:#999;font-size:13px;">読み込み中...</p>';
    el.style.display = '';
    try {
        const histories = await API.get(`/api/me/answer-history?plan_id=${planId}`);
        if (histories.length === 0) {
            el.innerHTML = '<p style="color:#bbb;font-size:13px;">変更履歴はありません</p>';
            return;
        }

        // 項目ごとにグループ化 (var_name をキーに、出現順を維持)
        const groups = new Map();
        for (const h of histories) {
            const key = h.var_name;
            if (!groups.has(key)) groups.set(key, { label: h.label, items: [] });
            groups.get(key).items.push(h);
        }

        const tabId = `htab-${planId}`;
        const keys = [...groups.keys()];
        const tabs = keys.map((k, i) => {
            const g = groups.get(k);
            return `<button class="history-tab${i === 0 ? ' active' : ''}" data-target="${tabId}-${i}" onclick="switchHistoryTab(this)">${esc(g.label)}</button>`;
        }).join('');

        const panels = keys.map((k, i) => {
            const g = groups.get(k);
            // タイムライン構築: 最初のold_value → 各new_value を時系列表示
            const timeline = [];
            if (g.items.length > 0 && g.items[0].old_value) {
                timeline.push({ date: null, value: g.items[0].old_value });
            }
            for (const h of g.items) {
                timeline.push({ date: h.changed_at, value: h.new_value });
            }

            return `
            <div class="history-panel${i === 0 ? ' active' : ''}" id="${tabId}-${i}">
                <div class="history-timeline">
                    ${timeline.map((t, ti) => {
                        const isLast = ti === timeline.length - 1;
                        const dateStr = t.date
                            ? new Date(t.date).toLocaleDateString('ja-JP', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                            : '初期値';
                        // 配列JSON（checkbox/array型）をカンマ区切りに変換
                        let displayVal = t.value || '-';
                        try {
                            const parsed = JSON.parse(displayVal);
                            if (Array.isArray(parsed)) {
                                displayVal = parsed.length > 0 ? parsed.join(', ') : '未設定';
                            }
                        } catch { /* JSONでなければそのまま */ }
                        return `
                        <div class="tl-row${isLast ? ' tl-current' : ''}">
                            <div class="tl-dot"></div>
                            <div class="tl-content">
                                <span class="tl-date">${esc(dateStr)}</span>
                                <span class="tl-value">${esc(displayVal)}${isLast ? ' <span class="tl-badge">現在</span>' : ''}</span>
                            </div>
                        </div>`;
                    }).join('')}
                </div>
            </div>`;
        }).join('');

        el.innerHTML = `
            <div style="font-size:12px;color:#999;font-weight:600;margin-bottom:6px;letter-spacing:.03em;">項目を選択</div>
            <div class="history-tabs">${tabs}</div>
            ${panels}
        `;
    } catch (e) {
        el.innerHTML = `<p style="color:#c00;font-size:13px;">${esc(e.message)}</p>`;
    }
}

function switchHistoryTab(btn) {
    const parent = btn.closest('.dash-card') || btn.parentElement.parentElement;
    parent.querySelectorAll('.history-tab').forEach(t => t.classList.remove('active'));
    parent.querySelectorAll('.history-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const panel = document.getElementById(btn.dataset.target);
    if (panel) panel.classList.add('active');
}

// --- 配信履歴 ---
let currentHistoryPage = 1;
async function loadHistoryCard() {
    const wrapper = document.getElementById('history-card');
    try {
        const data = await API.get(`/api/me/delivery-history?page=1&per_page=5`);
        if (data.items.length === 0) {
            wrapper.innerHTML = '';
            return;
        }
        wrapper.innerHTML = `
            <div class="dash-card">
                <div class="dash-card-title">最近の配信</div>
                <div id="history-list">
                    ${data.items.map(i => `
                        <div class="answer-row">
                            <span class="answer-label" style="min-width:auto;">${esc(i.subject)}</span>
                            <span class="answer-value" style="color:#999;font-size:12px;">${i.sent_at ? fmtDate(i.sent_at) : '-'}</span>
                        </div>
                    `).join('')}
                </div>
                ${data.total > 5 ? `
                <div style="margin-top:12px;">
                    <button class="d-btn d-btn-ghost d-btn-sm" onclick="expandHistory()">すべて表示</button>
                </div>` : ''}
                <div id="history-expanded" style="display:none;"></div>
            </div>`;
    } catch {
        wrapper.innerHTML = '';
    }
}

async function expandHistory() {
    const el = document.getElementById('history-expanded');
    if (el.style.display !== 'none') { el.style.display = 'none'; return; }
    el.style.display = '';
    el.innerHTML = '<p style="color:#999;font-size:13px;">読み込み中...</p>';
    await loadHistoryPage(1);
}

async function loadHistoryPage(page) {
    currentHistoryPage = page;
    const el = document.getElementById('history-expanded');
    try {
        const data = await API.get(`/api/me/delivery-history?page=${page}&per_page=20`);
        el.innerHTML = `
            ${data.items.map(i => `
                <div class="answer-row">
                    <span class="answer-label" style="min-width:auto;">${esc(i.subject)}</span>
                    <span class="answer-value" style="color:#999;font-size:12px;">${i.sent_at ? fmtDate(i.sent_at) : '-'}</span>
                </div>
            `).join('')}
            ${renderHistoryPagination(data.total, 20, page)}`;
    } catch (e) {
        el.innerHTML = `<p style="color:#c00;font-size:13px;">${esc(e.message)}</p>`;
    }
}

function renderHistoryPagination(total, perPage, current) {
    const pages = Math.ceil(total / perPage);
    if (pages <= 1) return '';
    let html = '<div style="display:flex;gap:4px;justify-content:center;margin-top:12px;">';
    for (let i = 1; i <= pages; i++) {
        const active = i === current ? 'background:#111;color:#fff;' : 'background:#f2f2f2;color:#333;';
        html += `<button onclick="loadHistoryPage(${i})" style="padding:4px 10px;border:none;border-radius:6px;cursor:pointer;font-size:12px;${active}">${i}</button>`;
    }
    return html + '</div>';
}

// --- 決済情報 ---
async function openBillingPortal() {
    try {
        const res = await API.post('/api/billing-portal', {});
        if (res.portal_url) location.href = res.portal_url;
    } catch (e) {
        alert(e.message);
    }
}

// --- ログアウト ---
async function logout() {
    try { await API.post('/api/auth/logout'); } catch {}
    localStorage.removeItem('csrf_token');
    location.href = '/login.html';
}

// --- 起動 ---
loadDashboard();
