/**
 * プロモーションコード管理UI
 */
let _promoPlans = [];

const PromotionsPage = {
    async render(container) {
        container.innerHTML = `
            <div class="content-header flex-between">
                <h1>プロモーションコード</h1>
                <button class="btn" onclick="PromotionsPage.showCreate()">新規作成</button>
            </div>
            <div id="promos-list" class="loading">読み込み中...</div>
            <div class="modal" id="promo-modal">
                <div class="modal-content">
                    <div class="modal-header">
                        <h2>プロモーションコード作成</h2>
                        <button class="close-btn" onclick="PromotionsPage.closeModal()">&times;</button>
                    </div>
                    <div class="form-group"><label>コード</label><input id="promo-code" type="text" placeholder="SUMMER2025"></div>
                    <div class="form-group">
                        <label>割引タイプ</label>
                        <select id="promo-type">
                            <option value="percent_off">割引率 (%)</option>
                            <option value="amount_off">割引額 (円)</option>
                        </select>
                    </div>
                    <div class="form-group"><label>割引値</label><input id="promo-value" type="number" min="1"></div>
                    <div class="form-group"><label>最大使用回数 (空欄=無制限)</label><input id="promo-max" type="number" min="1"></div>
                    <div class="form-group"><label>有効期限</label><input id="promo-expires" type="date"></div>
                    <div class="form-group">
                        <label>適用プラン (未選択=全プラン)</label>
                        <div id="promo-plans-checkboxes" style="margin-top:6px;"></div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="PromotionsPage.closeModal()">キャンセル</button>
                        <button class="btn" onclick="PromotionsPage.create()">作成</button>
                    </div>
                    <div id="promo-error" class="error-message"></div>
                </div>
            </div>
        `;
        await this.load();
    },

    async load() {
        try {
            const [promos, plans] = await Promise.all([
                API.get('/api/admin/promotions'),
                API.get('/api/admin/plans').catch(() => []),
            ]);
            _promoPlans = plans;
            const planMap = {};
            for (const p of plans) planMap[p.id] = p.name;

            const el = document.getElementById('promos-list');
            el.classList.remove('loading');
            if (promos.length === 0) {
                el.innerHTML = '<p>プロモーションコードがありません</p>';
                return;
            }
            el.innerHTML = `
                <div class="table-container"><table>
                    <thead><tr><th>コード</th><th>割引</th><th>使用数</th><th>上限</th><th>適用プラン</th><th>有効期限</th><th>状態</th><th>操作</th></tr></thead>
                    <tbody>${promos.map(p => {
                        let planLabel = '全プラン';
                        if (p.eligible_plan_ids && p.eligible_plan_ids.length > 0) {
                            planLabel = p.eligible_plan_ids.map(id => planMap[id] || `ID:${id}`).join(', ');
                        }
                        return `
                        <tr>
                            <td><strong>${p.code}</strong></td>
                            <td>${p.discount_type === 'percent_off' ? p.discount_value + '%' : '¥' + p.discount_value.toLocaleString()}</td>
                            <td>${p.times_redeemed}</td>
                            <td>${p.max_redemptions || '無制限'}</td>
                            <td>${planLabel}</td>
                            <td>${p.expires_at ? new Date(p.expires_at).toLocaleDateString('ja-JP') : '-'}</td>
                            <td><span class="badge ${p.is_active ? 'badge-active' : 'badge-inactive'}">${p.is_active ? '有効' : '無効'}</span></td>
                            <td>${p.is_active ? `<button class="btn btn-sm btn-danger" onclick="PromotionsPage.deactivate(${p.id})">無効化</button>` : ''}</td>
                        </tr>`;
                    }).join('')}</tbody>
                </table></div>
            `;
        } catch (e) {
            document.getElementById('promos-list').innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    async showCreate() {
        document.getElementById('promo-modal').classList.add('active');
        document.getElementById('promo-error').textContent = '';

        // プラン一覧をチェックボックスで表示
        const container = document.getElementById('promo-plans-checkboxes');
        try {
            if (_promoPlans.length === 0) {
                _promoPlans = await API.get('/api/admin/plans').catch(() => []);
            }
            if (_promoPlans.length === 0) {
                container.innerHTML = '<span style="color:#999;font-size:13px;">プランがありません</span>';
                return;
            }
            container.innerHTML = _promoPlans.map(p => `
                <label style="display:block;margin-bottom:4px;cursor:pointer;">
                    <input type="checkbox" class="promo-plan-check" value="${p.id}"> ${p.name} (¥${p.price.toLocaleString()}/月)
                </label>
            `).join('');
        } catch {
            container.innerHTML = '<span style="color:#999;font-size:13px;">プラン読込失敗</span>';
        }
    },

    closeModal() {
        document.getElementById('promo-modal').classList.remove('active');
    },

    async create() {
        const errEl = document.getElementById('promo-error');
        errEl.textContent = '';
        const code = document.getElementById('promo-code').value.trim();
        const value = parseInt(document.getElementById('promo-value').value);
        if (!code || !value) { errEl.textContent = 'コードと割引値は必須です'; return; }

        // 選択されたプランIDを収集
        const checkedIds = [];
        document.querySelectorAll('.promo-plan-check:checked').forEach(el => {
            checkedIds.push(parseInt(el.value));
        });

        try {
            await API.post('/api/admin/promotions', {
                code,
                discount_type: document.getElementById('promo-type').value,
                discount_value: value,
                max_redemptions: parseInt(document.getElementById('promo-max').value) || null,
                expires_at: document.getElementById('promo-expires').value || null,
                eligible_plan_ids: checkedIds.length > 0 ? checkedIds : null,
            });
            this.closeModal();
            await this.load();
        } catch (e) {
            errEl.textContent = e.message;
        }
    },

    async deactivate(id) {
        if (!confirm('このプロモーションコードを無効化しますか？')) return;
        try {
            await API.put(`/api/admin/promotions/${id}/deactivate`);
            await this.load();
        } catch (e) {
            alert(e.message);
        }
    },
};
