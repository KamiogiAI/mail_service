/**
 * ユーザー管理UI
 */
const UsersPage = {
    currentPage: 1,
    allPlans: [],

    async render(container) {
        container.innerHTML = `
            <div class="content-header flex-between">
                <h1>ユーザー管理</h1>
                <button class="btn" onclick="UsersPage.showInvite()">管理者招待</button>
            </div>
            <div class="filters">
                <input id="user-search" type="text" placeholder="検索 (メール/会員番号/名前)" style="flex:1;padding:8px;border:1px solid #000;" onkeydown="if(event.key==='Enter')UsersPage.search()">
                <button class="btn btn-secondary" onclick="UsersPage.search()">検索</button>
                <select id="user-role-filter" onchange="UsersPage.search()" style="padding:8px;border:1px solid #000;">
                    <option value="">全ロール</option>
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                </select>
            </div>
            <div id="users-list">読み込み中...</div>

            <!-- 管理者招待モーダル -->
            <div class="modal" id="invite-modal">
                <div class="modal-content">
                    <div class="modal-header"><h2>管理者招待</h2><button class="close-btn" onclick="document.getElementById('invite-modal').classList.remove('active')">&times;</button></div>
                    <div class="form-group"><label>メール</label><input id="inv-email" type="email"></div>
                    <div class="form-group"><label>姓</label><input id="inv-last"></div>
                    <div class="form-group"><label>名</label><input id="inv-first"></div>
                    <div class="modal-footer"><button class="btn" onclick="UsersPage.invite()">招待</button></div>
                    <div id="invite-msg"></div>
                </div>
            </div>

            <!-- プラン変更モーダル -->
            <div class="modal" id="plan-change-modal">
                <div class="modal-content">
                    <div class="modal-header"><h2>加入プラン変更</h2><button class="close-btn" onclick="UsersPage.closePlanModal()">&times;</button></div>
                    <p id="pcm-user-label" style="margin-bottom:15px;font-weight:600;"></p>
                    <div id="pcm-plans">読み込み中...</div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="UsersPage.closePlanModal()">キャンセル</button>
                        <button class="btn" onclick="UsersPage.savePlans()">保存</button>
                    </div>
                    <div id="pcm-msg"></div>
                </div>
            </div>
        `;
        // プラン一覧を事前取得
        try { this.allPlans = await API.get('/api/admin/plans'); } catch { this.allPlans = []; }
        await this.load(1);
    },

    async load(page) {
        this.currentPage = page;
        const search = document.getElementById('user-search')?.value || '';
        const role = document.getElementById('user-role-filter')?.value || '';
        try {
            const params = new URLSearchParams({page, per_page: 50});
            if (search) params.set('search', search);
            if (role) params.set('role', role);
            const data = await API.get(`/api/admin/users?${params}`);
            const el = document.getElementById('users-list');
            el.innerHTML = `
                <div class="table-container"><table>
                    <thead><tr><th>会員番号</th><th>名前</th><th>メール</th><th>加入プラン</th><th>ロール</th><th>状態</th><th>操作</th></tr></thead>
                    <tbody>${data.users.map(u => {
                        const planBadges = u.plans.length > 0
                            ? u.plans.map(p => `<span class="badge badge-active" style="margin:2px;">${this.esc(p.plan_name)}</span>`).join('')
                            : '<span style="color:#999;">なし</span>';
                        return `
                        <tr>
                            <td>${u.member_no}</td>
                            <td>${this.esc(u.name_last)} ${this.esc(u.name_first)}</td>
                            <td>${this.esc(u.email)}</td>
                            <td>${planBadges}</td>
                            <td>${u.role}</td>
                            <td>${u.is_active ? '<span class="badge badge-active">有効</span>' : '<span class="badge badge-inactive">無効</span>'}</td>
                            <td class="action-btns">
                                <button class="btn btn-sm btn-secondary" onclick="UsersPage.showPlanModal(${u.id},'${this.esc(u.name_last)} ${this.esc(u.name_first)}',${JSON.stringify(u.plans.map(p=>p.plan_id)).replace(/"/g,'&quot;')})">プラン変更</button>
                                <button class="btn btn-sm btn-secondary" onclick="UsersPage.toggleActive(${u.id})">${u.is_active ? '無効化' : '有効化'}</button>
                                <button class="btn btn-sm btn-secondary" onclick="UsersPage.changeRole(${u.id},'${u.role==='admin'?'user':'admin'}')">${u.role==='admin'?'→user':'→admin'}</button>
                            </td>
                        </tr>`;
                    }).join('')}</tbody>
                </table></div>
                <p style="margin-top:10px;color:#666;">${data.total}件中 ${(page-1)*50+1}-${Math.min(page*50,data.total)}件</p>
            `;
        } catch (e) {
            document.getElementById('users-list').innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    search() { this.load(1); },

    // --- プラン変更モーダル ---
    editingUserId: null,

    showPlanModal(userId, userName, currentPlanIds) {
        this.editingUserId = userId;
        document.getElementById('pcm-user-label').textContent = `${userName} (ID: ${userId})`;
        document.getElementById('pcm-msg').innerHTML = '';

        const container = document.getElementById('pcm-plans');
        if (this.allPlans.length === 0) {
            container.innerHTML = '<p>利用可能なプランがありません</p>';
        } else {
            container.innerHTML = this.allPlans.map(p => {
                const checked = currentPlanIds.includes(p.id) ? 'checked' : '';
                return `
                    <label class="plan-check-row">
                        <input type="checkbox" value="${p.id}" class="pcm-cb" ${checked}>
                        <span>${this.esc(p.name)}</span>
                        <span style="color:#666;font-size:12px;">¥${p.price.toLocaleString()}/月</span>
                        ${!p.is_active ? '<span class="badge badge-inactive" style="margin-left:5px;">無効</span>' : ''}
                    </label>
                `;
            }).join('');
        }

        document.getElementById('plan-change-modal').classList.add('active');
    },

    closePlanModal() {
        document.getElementById('plan-change-modal').classList.remove('active');
    },

    async savePlans() {
        const planIds = Array.from(document.querySelectorAll('.pcm-cb:checked')).map(cb => parseInt(cb.value));
        const msgEl = document.getElementById('pcm-msg');
        msgEl.innerHTML = '';
        try {
            const res = await API.put(`/api/admin/users/${this.editingUserId}/subscriptions`, { plan_ids: planIds });
            msgEl.innerHTML = `<p class="success-message">${res.message}</p>`;
            setTimeout(() => {
                this.closePlanModal();
                this.load(this.currentPage);
            }, 500);
        } catch (e) {
            msgEl.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    // --- 既存操作 ---
    async toggleActive(id) {
        try { await API.put(`/api/admin/users/${id}/toggle-active`); this.load(this.currentPage); } catch(e) { alert(e.message); }
    },

    async changeRole(id, role) {
        if (!confirm(`ロールを${role}に変更しますか？`)) return;
        try { await API.put(`/api/admin/users/${id}/role`, {role}); this.load(this.currentPage); } catch(e) { alert(e.message); }
    },

    showInvite() { document.getElementById('invite-modal').classList.add('active'); },

    async invite() {
        try {
            const res = await API.post('/api/admin/users/invite-admin', {
                email: document.getElementById('inv-email').value,
                name_last: document.getElementById('inv-last').value,
                name_first: document.getElementById('inv-first').value,
            });
            const msg = this.esc(res.message);
            const pwdHtml = res.temp_password ? '<br>仮パスワード: <code style="background:#f5f5f5;padding:2px 6px;">' + this.esc(res.temp_password) + '</code>' : '';
            document.getElementById('invite-msg').innerHTML = `<p class="success-message">${msg}${pwdHtml}</p>`;
        } catch(e) {
            document.getElementById('invite-msg').innerHTML = `<p class="error-message">${this.esc(e.message)}</p>`;
        }
    },

    esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; },
};
