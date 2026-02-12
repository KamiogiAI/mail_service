/**
 * 手動送信UI (タブ切替: 個別送信 / 全員送信)
 */
const ManualSendPage = {
    plans: [],
    mode: 'user', // 'user' or 'plan'
    selectedUsers: [], // [{id, member_no, name, email}]

    async render(container) {
        this.selectedUsers = [];
        container.innerHTML = `
            <div class="content-header"><h1>手動送信</h1></div>
            <div class="card">
                <div class="tabs" id="ms-tabs">
                    <button class="tab-btn active" onclick="ManualSendPage.switchMode('user')">個別送信</button>
                    <button class="tab-btn" onclick="ManualSendPage.switchMode('plan')">全員送信</button>
                </div>

                <div id="ms-mode-user" class="tab-content active">
                    <div class="form-group">
                        <label>ユーザー選択 <small>(ID or 会員番号を入力してスペースで確定)</small></label>
                        <div class="tag-input-container" id="ms-tag-container">
                            <div id="ms-selected-tags"></div>
                            <input id="ms-user-input" type="text" placeholder="ID or 会員番号を入力..." 
                                   onkeydown="ManualSendPage.handleKeyDown(event)">
                        </div>
                    </div>
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
            if (this.selectedUsers.length === 0) {
                resultEl.innerHTML = '<p class="error-message">送信先ユーザーを選択してください</p>';
                btn.disabled = false;
                return;
            }
            resultEl.innerHTML = `<p>送信中... (${this.selectedUsers.length}人)</p>`;
            let successCount = 0;
            let failCount = 0;
            const errors = [];
            
            for (const user of this.selectedUsers) {
                try {
                    await API.post('/api/admin/manual-send/user', {
                        user_id: user.id,
                        subject: subject,
                        body: body,
                    });
                    successCount++;
                } catch (e) {
                    failCount++;
                    errors.push(`${user.name}: ${e.message}`);
                }
            }
            
            if (failCount === 0) {
                resultEl.innerHTML = `<p class="success-message">送信完了 (${successCount}人)</p>`;
                this.selectedUsers = [];
                this.renderTags();
            } else {
                resultEl.innerHTML = `<p class="error-message">成功: ${successCount}人, 失敗: ${failCount}人<br>${errors.join('<br>')}</p>`;
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
            resultEl.innerHTML = '<p>送信開始中...</p>';
            try {
                const res = await API.post('/api/admin/manual-send/plan', {
                    plan_id: planId,
                    subject: subject,
                    body: body,
                });
                
                if (res.status === 'running' && res.delivery_id) {
                    // バックグラウンド実行中 → 進捗をポーリング
                    resultEl.innerHTML = `
                        <p>送信中... (${res.total_count}件)</p>
                        <div class="progress-bar-container">
                            <div class="progress-bar" id="ms-progress-bar" style="width: 0%"></div>
                        </div>
                        <p id="ms-progress-text">0 / ${res.total_count}</p>
                    `;
                    this.pollDeliveryProgress(res.delivery_id, res.total_count, resultEl, btn);
                    return; // ボタンはポーリング完了後に有効化
                } else {
                    resultEl.innerHTML = `<p class="success-message">${res.message}</p>`;
                }
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

    async handleKeyDown(event) {
        if (event.key !== ' ' && event.key !== 'Enter') return;
        
        const input = document.getElementById('ms-user-input');
        const value = input.value.trim();
        if (!value) return;
        
        event.preventDefault();
        input.disabled = true;
        
        try {
            // IDか会員番号かを判定して検索
            const isNumeric = /^\d+$/.test(value);
            let user = null;
            
            if (isNumeric && value.length <= 5) {
                // 短い数字はuser_idとして検索
                user = await API.get(`/api/admin/users/${value}`);
            } else {
                // 会員番号として検索
                const users = await API.get(`/api/admin/users?search=${encodeURIComponent(value)}&per_page=1`);
                if (users.users && users.users.length > 0) {
                    user = users.users[0];
                }
            }
            
            if (user && !this.selectedUsers.find(u => u.id === user.id)) {
                this.selectedUsers.push({
                    id: user.id,
                    member_no: user.member_no,
                    name: `${user.name_last} ${user.name_first}`,
                    email: user.email,
                });
                this.renderTags();
            } else if (!user) {
                alert('ユーザーが見つかりません: ' + value);
            }
        } catch (e) {
            alert('ユーザー検索エラー: ' + e.message);
        }
        
        input.value = '';
        input.disabled = false;
        input.focus();
    },

    renderTags() {
        const container = document.getElementById('ms-selected-tags');
        container.innerHTML = this.selectedUsers.map((u, i) => `
            <span class="user-tag">
                <span class="tag-name">${this.esc(u.name)}</span>
                <span class="tag-id">(${this.esc(u.member_no)})</span>
                <button type="button" class="tag-remove" onclick="ManualSendPage.removeUser(${i})">&times;</button>
            </span>
        `).join('');
    },

    removeUser(index) {
        this.selectedUsers.splice(index, 1);
        this.renderTags();
    },

    async pollDeliveryProgress(deliveryId, totalCount, resultEl, btn) {
        const checkProgress = async () => {
            try {
                const deliveries = await API.get('/api/admin/deliveries?limit=10');
                const delivery = deliveries.find(d => d.id === deliveryId);
                
                if (!delivery) {
                    resultEl.innerHTML = '<p class="error-message">配信情報が見つかりません</p>';
                    btn.disabled = false;
                    return;
                }
                
                const success = delivery.success_count || 0;
                const fail = delivery.fail_count || 0;
                const progress = success + fail;
                const percent = Math.round((progress / totalCount) * 100);
                
                const progressBar = document.getElementById('ms-progress-bar');
                const progressText = document.getElementById('ms-progress-text');
                
                if (progressBar) progressBar.style.width = `${percent}%`;
                if (progressText) progressText.textContent = `${progress} / ${totalCount}`;
                
                if (delivery.status !== 'running') {
                    // 完了
                    if (delivery.status === 'success') {
                        resultEl.innerHTML = `<p class="success-message">送信完了 (成功: ${success}件)</p>`;
                    } else if (delivery.status === 'partial_failed') {
                        resultEl.innerHTML = `<p class="error-message">送信完了 (成功: ${success}件, 失敗: ${fail}件)</p>`;
                    } else {
                        resultEl.innerHTML = `<p class="error-message">送信失敗</p>`;
                    }
                    btn.disabled = false;
                    return;
                }
                
                // まだ実行中 → 3秒後に再確認
                setTimeout(checkProgress, 3000);
            } catch (e) {
                resultEl.innerHTML = `<p class="error-message">進捗確認エラー: ${e.message}</p>`;
                btn.disabled = false;
            }
        };
        
        // 最初のチェックは2秒後
        setTimeout(checkProgress, 2000);
    },
};
