/**
 * 手動送信UI (タブ切替: 個別送信 / 全員送信)
 */
const ManualSendPage = {
    plans: [],
    mode: 'user', // 'user' or 'plan'

    async render(container) {
        container.innerHTML = `
            <div class="content-header"><h1>手動送信</h1></div>
            <div class="card">
                <div class="tabs" id="ms-tabs">
                    <button class="tab-btn active" onclick="ManualSendPage.switchMode('user')">個別送信</button>
                    <button class="tab-btn" onclick="ManualSendPage.switchMode('plan')">全員送信</button>
                </div>

                <div id="ms-mode-user" class="tab-content active">
                    <div class="form-group"><label>ユーザーID</label><input id="ms-user-id" type="number" placeholder="ユーザーIDを入力"></div>
                </div>

                <div id="ms-mode-plan" class="tab-content">
                    <div class="form-group">
                        <label>プラン</label>
                        <select id="ms-plan-id"><option value="">読み込み中...</option></select>
                    </div>
                </div>

                <div class="form-group"><label>件名</label><input id="ms-subject" type="text" placeholder="メールの件名"></div>
                <div class="form-group"><label>本文</label><textarea id="ms-body" rows="10" placeholder="メール本文を入力"></textarea></div>

                <button class="btn" id="ms-send-btn" onclick="ManualSendPage.send()">送信</button>
                <div id="ms-result" style="margin-top:15px;"></div>
            </div>
        `;
        await this.loadPlans();
    },

    async loadPlans() {
        try {
            this.plans = await API.get('/api/admin/plans');
            const sel = document.getElementById('ms-plan-id');
            if (!sel) return;
            sel.innerHTML = '<option value="">プランを選択</option>' +
                this.plans.map(p => `<option value="${p.id}">${this.esc(p.name)} (加入者: ${p.subscriber_count})</option>`).join('');
        } catch (e) {
            const sel = document.getElementById('ms-plan-id');
            if (sel) sel.innerHTML = '<option value="">読み込み失敗</option>';
        }
    },

    switchMode(mode) {
        this.mode = mode;
        document.querySelectorAll('#ms-tabs .tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.card > .tab-content').forEach(c => c.classList.remove('active'));
        if (mode === 'user') {
            document.querySelector('#ms-tabs .tab-btn:first-child').classList.add('active');
            document.getElementById('ms-mode-user').classList.add('active');
        } else {
            document.querySelector('#ms-tabs .tab-btn:last-child').classList.add('active');
            document.getElementById('ms-mode-plan').classList.add('active');
        }
    },

    async send() {
        const resultEl = document.getElementById('ms-result');
        const subject = document.getElementById('ms-subject').value;
        const body = document.getElementById('ms-body').value;

        if (!subject.trim() || !body.trim()) {
            resultEl.innerHTML = '<p class="error-message">件名と本文は必須です</p>';
            return;
        }

        const btn = document.getElementById('ms-send-btn');
        btn.disabled = true;

        if (this.mode === 'user') {
            const userId = parseInt(document.getElementById('ms-user-id').value);
            if (!userId) {
                resultEl.innerHTML = '<p class="error-message">ユーザーIDを入力してください</p>';
                btn.disabled = false;
                return;
            }
            resultEl.innerHTML = '<p>送信中...</p>';
            try {
                const res = await API.post('/api/admin/manual-send/user', {
                    user_id: userId,
                    subject: subject,
                    body: body,
                });
                resultEl.innerHTML = `<p class="success-message">${res.message}</p>`;
            } catch (e) {
                resultEl.innerHTML = `<p class="error-message">${e.message}</p>`;
            }
        } else {
            const planId = parseInt(document.getElementById('ms-plan-id').value);
            if (!planId) {
                resultEl.innerHTML = '<p class="error-message">プランを選択してください</p>';
                btn.disabled = false;
                return;
            }
            if (!confirm('選択したプランの全加入者にメールを送信します。よろしいですか？')) {
                btn.disabled = false;
                return;
            }
            resultEl.innerHTML = '<p>送信中... (全ユーザーへの送信には時間がかかります)</p>';
            try {
                const res = await API.post('/api/admin/manual-send/plan', {
                    plan_id: planId,
                    subject: subject,
                    body: body,
                });
                resultEl.innerHTML = `<p class="success-message">${res.message} (成功: ${res.success_count}, 失敗: ${res.fail_count})</p>`;
            } catch (e) {
                resultEl.innerHTML = `<p class="error-message">${e.message}</p>`;
            }
        }
        btn.disabled = false;
    },

    esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    },
};
