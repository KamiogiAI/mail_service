/**
 * 購読管理UI (プラン別タブ表示 + 詳細モーダル)
 */
const SubscriptionsPage = {
    plans: [],
    activeTab: 0,
    currentDetail: null,
    editMode: false,

    STATUS_LABELS: {
        active: '有効',
        trialing: 'トライアル',
        past_due: '支払い遅延',
        admin_added: '管理者追加',
    },

    async render(container) {
        container.innerHTML = `
            <div class="content-header"><h1>購読管理</h1></div>
            <div id="subs-content">読み込み中...</div>
            <div class="modal" id="sub-detail-modal">
                <div class="modal-content" style="max-width:900px;">
                    <div class="modal-header">
                        <h2 id="sub-detail-title">購読詳細</h2>
                        <button class="close-btn" onclick="SubscriptionsPage.closeDetail()">&times;</button>
                    </div>
                    <div id="sub-detail-body">読み込み中...</div>
                    <div class="modal-footer" id="sub-detail-footer">
                        <button class="btn btn-secondary" onclick="SubscriptionsPage.closeDetail()">閉じる</button>
                        <button class="btn btn-secondary" id="sub-detail-edit-btn" style="display:none;" onclick="SubscriptionsPage.toggleEditMode()">回答を変更</button>
                        <button class="btn" id="sub-detail-save-btn" style="display:none;" onclick="SubscriptionsPage.saveAnswers()">保存</button>
                        <button class="btn btn-secondary" id="sub-detail-cancel-btn" style="display:none;" onclick="SubscriptionsPage.cancelEdit()">キャンセル</button>
                    </div>
                </div>
            </div>
        `;
        await this.load();
    },

    async load() {
        const el = document.getElementById('subs-content');
        try {
            this.plans = await API.get('/api/admin/subscriptions');
            if (this.plans.length === 0) {
                el.innerHTML = '<p>有効な購読がありません</p>';
                return;
            }
            this.activeTab = 0;
            this.renderTabs();
        } catch (e) {
            el.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    renderTabs() {
        const el = document.getElementById('subs-content');
        const tabsHtml = this.plans.map((p, i) => `
            <button class="tab-btn ${i === this.activeTab ? 'active' : ''}"
                onclick="SubscriptionsPage.switchTab(${i})">${this.esc(p.plan_name)} (${p.subscriber_count})</button>
        `).join('');

        el.innerHTML = `
            <div class="tabs">${tabsHtml}</div>
            <div id="subs-tab-content"></div>
        `;
        this.renderTabContent();
    },

    switchTab(idx) {
        this.activeTab = idx;
        document.querySelectorAll('#subs-content .tab-btn').forEach((b, i) => {
            b.classList.toggle('active', i === idx);
        });
        this.renderTabContent();
    },

    renderTabContent() {
        const p = this.plans[this.activeTab];
        const el = document.getElementById('subs-tab-content');

        // サマリーカード
        const summaryHtml = `
            <div class="card" style="margin-bottom:20px;">
                <div class="subs-summary">
                    <div class="subs-summary-item">
                        <div class="subs-summary-value">${p.subscriber_count}</div>
                        <div class="subs-summary-label">加入者数</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-value">&yen;${p.total_monthly_revenue.toLocaleString()}</div>
                        <div class="subs-summary-label">月額合計</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-value">${p.active_count}</div>
                        <div class="subs-summary-label">有効</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-value">${p.trialing_count}</div>
                        <div class="subs-summary-label">トライアル</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-value">${p.admin_added_count || 0}</div>
                        <div class="subs-summary-label">管理者追加</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-value">${p.cancel_scheduled_count}</div>
                        <div class="subs-summary-label">解約予定</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-value">&yen;${p.price.toLocaleString()}/月</div>
                        <div class="subs-summary-label">プラン単価</div>
                    </div>
                </div>
            </div>
        `;

        // テーブル
        const rows = p.subscribers.map(s => {
            let statusLabel = this.STATUS_LABELS[s.status] || s.status;
            let statusClass = 'badge-active';
            if (s.cancel_at_period_end) {
                statusLabel = '解約予定';
                statusClass = 'badge-warning';
            } else if (s.status === 'trialing') {
                statusClass = 'badge-active';
            } else if (s.status === 'past_due') {
                statusClass = 'badge-danger';
            } else if (s.status === 'admin_added') {
                statusClass = 'badge-waiting';
            }

            let dateLabel = '-';
            if (s.cancel_at_period_end && s.current_period_end) {
                dateLabel = this.fmtDate(s.current_period_end) + ' (終了)';
            } else if (s.status === 'trialing' && s.trial_end) {
                dateLabel = this.fmtDate(s.trial_end) + ' (トライアル終了)';
            } else if (s.current_period_end) {
                dateLabel = this.fmtDate(s.current_period_end) + ' (更新)';
            }

            return `
                <tr>
                    <td>${this.esc(s.member_no)}</td>
                    <td>${this.esc(s.name)}</td>
                    <td>${this.esc(s.email)}</td>
                    <td><span class="badge ${statusClass}">${statusLabel}</span></td>
                    <td>${dateLabel}</td>
                    <td><button class="btn btn-sm btn-secondary" onclick="SubscriptionsPage.showDetail(${s.subscription_id})">詳細</button></td>
                </tr>
            `;
        }).join('');

        el.innerHTML = summaryHtml + `
            <div class="card">
                <div class="table-container"><table>
                    <thead><tr>
                        <th>会員番号</th><th>名前</th><th>メール</th><th>ステータス</th><th>更新日 / 終了日</th><th>操作</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                </table></div>
            </div>
        `;
    },

    // --- 詳細モーダル ---

    async showDetail(subscriptionId) {
        const modal = document.getElementById('sub-detail-modal');
        const body = document.getElementById('sub-detail-body');
        modal.classList.add('active');
        body.innerHTML = '<p>読み込み中...</p>';
        this.editMode = false;
        this.updateFooterButtons();

        try {
            const data = await API.get(`/api/admin/subscriptions/${subscriptionId}/detail`);
            this.currentDetail = data;
            this.renderDetail(data);
        } catch (e) {
            body.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    updateFooterButtons() {
        const editBtn = document.getElementById('sub-detail-edit-btn');
        const saveBtn = document.getElementById('sub-detail-save-btn');
        const cancelBtn = document.getElementById('sub-detail-cancel-btn');

        if (this.editMode) {
            editBtn.style.display = 'none';
            saveBtn.style.display = '';
            cancelBtn.style.display = '';
        } else {
            editBtn.style.display = this.currentDetail?.answers?.length > 0 && this.currentDetail?.user ? '' : 'none';
            saveBtn.style.display = 'none';
            cancelBtn.style.display = 'none';
        }
    },

    toggleEditMode() {
        this.editMode = true;
        this.updateFooterButtons();
        this.renderDetail(this.currentDetail);
    },

    cancelEdit() {
        this.editMode = false;
        this.updateFooterButtons();
        this.renderDetail(this.currentDetail);
    },

    renderDetail(data) {
        const body = document.getElementById('sub-detail-body');
        const sub = data.subscription;
        const user = data.user;
        const plan = data.plan;
        const answers = data.answers;

        // タイトル更新
        document.getElementById('sub-detail-title').textContent =
            plan ? `${plan.name} - 購読詳細` : '購読詳細';

        // ステータスバッジ
        const statusMap = {
            active: ['badge-active', '有効'],
            trialing: ['badge-active', 'トライアル'],
            past_due: ['badge-danger', '支払い遅延'],
            canceled: ['badge-inactive', '解約済'],
            unpaid: ['badge-danger', '未払い'],
            incomplete: ['badge-warning', '未完了'],
            admin_added: ['badge-waiting', '管理者追加'],
        };
        const [badgeClass, badgeLabel] = statusMap[sub.status] || ['badge-inactive', sub.status];
        const isAdminAdded = sub.status === 'admin_added';

        // 購読情報セクション
        let html = `
            <div style="margin-bottom:24px;">
                <h3 style="font-size:16px;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #ddd;">購読情報</h3>
                <div class="subs-summary" style="grid-template-columns:repeat(auto-fill,minmax(200px,1fr));">
                    <div class="subs-summary-item">
                        <div class="subs-summary-label">ステータス</div>
                        <div style="margin-top:4px;"><span class="badge ${badgeClass}">${badgeLabel}</span></div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-label">入会日</div>
                        <div class="subs-summary-value" style="font-size:14px;">${this.fmtDate(sub.created_at)}</div>
                    </div>
                    ${!isAdminAdded ? `
                    <div class="subs-summary-item">
                        <div class="subs-summary-label">トライアル終了日</div>
                        <div class="subs-summary-value" style="font-size:14px;">${this.fmtDate(sub.trial_end)}</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-label">現在の期間</div>
                        <div class="subs-summary-value" style="font-size:14px;">${this.fmtDate(sub.current_period_start)} ~ ${this.fmtDate(sub.current_period_end)}</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-label">解約予定</div>
                        <div class="subs-summary-value" style="font-size:14px;">${sub.cancel_at_period_end ? 'はい' : 'いいえ'}</div>
                    </div>
                    <div class="subs-summary-item">
                        <div class="subs-summary-label">Stripe ID</div>
                        <div class="subs-summary-value" style="font-size:11px;word-break:break-all;">${this.esc(sub.stripe_subscription_id || '-')}</div>
                    </div>
                    ` : ''}
                </div>
            </div>
        `;

        // ユーザー情報セクション
        if (user) {
            html += `
                <div style="margin-bottom:24px;">
                    <h3 style="font-size:16px;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #ddd;">ユーザー情報</h3>
                    <div class="subs-summary" style="grid-template-columns:repeat(auto-fill,minmax(200px,1fr));">
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">会員番号</div>
                            <div class="subs-summary-value" style="font-size:14px;">${this.esc(user.member_no)}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">名前</div>
                            <div class="subs-summary-value" style="font-size:14px;">${this.esc(user.name_last)} ${this.esc(user.name_first)}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">メール</div>
                            <div class="subs-summary-value" style="font-size:12px;word-break:break-all;">${this.esc(user.email)}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">トライアル使用済</div>
                            <div class="subs-summary-value" style="font-size:14px;">${user.trial_used ? 'はい' : 'いいえ'}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">配信可能</div>
                            <div class="subs-summary-value" style="font-size:14px;">${user.deliverable ? 'はい' : 'いいえ'}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">アカウント状態</div>
                            <div style="margin-top:4px;"><span class="badge ${user.is_active ? 'badge-active' : 'badge-inactive'}">${user.is_active ? '有効' : '無効'}</span></div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            html += `
                <div style="margin-bottom:24px;">
                    <h3 style="font-size:16px;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #ddd;">ユーザー情報</h3>
                    <p style="color:#999;">退会済みのため、ユーザー情報はありません</p>
                </div>
            `;
        }

        // 回答セクション
        html += `<div>
            <h3 style="font-size:16px;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #ddd;">質問回答</h3>`;

        if (!user) {
            html += '<p style="color:#999;">退会済みのため、回答の閲覧・編集はできません</p>';
        } else if (answers.length === 0) {
            html += '<p style="color:#999;">このプランには質問が設定されていません</p>';
        } else {
            if (this.editMode) {
                html += answers.map(q => this.renderAnswerField(q)).join('');
                html += '<span id="sd-save-msg" style="font-size:13px;margin-left:10px;"></span>';
            } else {
                html += answers.map(q => this.renderAnswerView(q)).join('');
            }
        }

        html += '</div>';
        body.innerHTML = html;
        this.updateFooterButtons();
    },

    renderAnswerView(q) {
        const carried = q.carried_over ? ' <span style="color:#999;font-size:11px;">(引き継ぎ)</span>' : '';
        let valueHtml = '';

        if (!q.answer) {
            valueHtml = '<span style="color:#999;">未回答</span>';
        } else if (q.question_type === 'checkbox' || q.question_type === 'array') {
            let vals = [];
            try { vals = JSON.parse(q.answer || '[]'); } catch {}
            if (vals.length === 0) {
                valueHtml = '<span style="color:#999;">未回答</span>';
            } else {
                valueHtml = vals.map(v => `<span style="display:inline-block;background:#f0f0f0;padding:2px 8px;margin:2px 4px 2px 0;border-radius:3px;font-size:13px;">${this.esc(v)}</span>`).join('');
            }
        } else {
            valueHtml = `<span style="font-size:14px;">${this.esc(q.answer)}</span>`;
        }

        return `
            <div style="margin-bottom:16px;padding:12px;background:#fafafa;border:1px solid #eee;">
                <div style="font-weight:600;font-size:13px;color:#666;margin-bottom:6px;">${this.esc(q.label)}${q.is_required ? ' *' : ''}${carried}</div>
                <div>${valueHtml}</div>
            </div>
        `;
    },

    renderAnswerField(q) {
        const val = this.esc(q.answer || '');
        const carried = q.carried_over ? ' <span style="color:#999;font-size:11px;">(引き継ぎ)</span>' : '';
        let input = '';

        switch (q.question_type) {
            case 'textarea':
                input = `<textarea class="sd-edit" data-qid="${q.question_id}" style="width:100%;min-height:80px;padding:8px;border:1px solid #000;font-family:inherit;font-size:14px;">${val}</textarea>`;
                break;
            case 'number':
                input = `<input class="sd-edit" data-qid="${q.question_id}" type="number" value="${val}" style="width:100%;padding:8px;border:1px solid #000;font-size:14px;">`;
                break;
            case 'date':
                input = `<input class="sd-edit" data-qid="${q.question_id}" type="date" value="${val}" style="width:100%;padding:8px;border:1px solid #000;font-size:14px;">`;
                break;
            case 'select':
                input = `<select class="sd-edit" data-qid="${q.question_id}" style="width:100%;padding:8px;border:1px solid #000;font-size:14px;">
                    <option value="">選択してください</option>
                    ${(q.options || []).map(o => `<option value="${this.esc(o)}" ${q.answer === o ? 'selected' : ''}>${this.esc(o)}</option>`).join('')}
                </select>`;
                break;
            case 'radio':
                input = `<div style="display:flex;flex-wrap:wrap;gap:12px;">` +
                    (q.options || []).map(o => `
                        <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;font-weight:normal;">
                            <input type="radio" name="sd-edit-radio-${q.question_id}" class="sd-edit-radio" data-qid="${q.question_id}" value="${this.esc(o)}" ${q.answer === o ? 'checked' : ''} style="width:auto;"> ${this.esc(o)}
                        </label>
                    `).join('') + `</div>`;
                break;
            case 'checkbox': {
                let checked = [];
                try { checked = JSON.parse(q.answer || '[]'); } catch {}
                input = `<div style="display:flex;flex-wrap:wrap;gap:12px;">` +
                    (q.options || []).map(o => `
                        <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;font-weight:normal;">
                            <input type="checkbox" class="sd-edit-check" data-qid="${q.question_id}" value="${this.esc(o)}" ${checked.includes(o) ? 'checked' : ''} style="width:auto;"> ${this.esc(o)}
                        </label>
                    `).join('') + `</div>`;
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
                    <div class="sd-array-item" style="display:flex;gap:8px;margin-bottom:6px;">
                        <input type="text" class="sd-array-input" data-qid="${q.question_id}" style="flex:1;padding:8px;border:1px solid #000;font-size:14px;" value="${this.esc(v)}">
                        ${showRemove ? `<button type="button" onclick="SubscriptionsPage.removeArrayItem(this)" style="background:#dc3545;color:#fff;border:none;padding:0 10px;cursor:pointer;font-size:16px;">×</button>` : ''}
                    </div>
                `).join('');
                input = `
                    <div class="sd-array-wrap" data-qid="${q.question_id}" data-max="${maxItems}" data-min="${minReq}">
                        <div class="sd-array-items">${items}</div>
                        <button type="button" onclick="SubscriptionsPage.addArrayItem(this.closest('.sd-array-wrap'))" style="background:#f5f5f5;border:1px solid #ddd;padding:4px 14px;cursor:pointer;font-size:13px;">+ 追加</button>
                        ${hintHtml}
                    </div>
                `;
                break;
            }
            default:
                input = `<input class="sd-edit" data-qid="${q.question_id}" type="text" value="${val}" style="width:100%;padding:8px;border:1px solid #000;font-size:14px;">`;
        }

        return `<div class="form-group"><label>${this.esc(q.label)}${q.is_required ? ' *' : ''}${carried}</label>${input}</div>`;
    },

    addArrayItem(container) {
        const max = parseInt(container.dataset.max) || 0;
        const qid = container.dataset.qid;
        const items = container.querySelectorAll('.sd-array-item');
        if (max > 0 && items.length >= max) {
            alert('最大' + max + '件までです');
            return;
        }
        if (items.length === 1 && !items[0].querySelector('button')) {
            items[0].insertAdjacentHTML('beforeend', `<button type="button" onclick="SubscriptionsPage.removeArrayItem(this)" style="background:#dc3545;color:#fff;border:none;padding:0 10px;cursor:pointer;font-size:16px;">×</button>`);
        }
        const div = document.createElement('div');
        div.className = 'sd-array-item';
        div.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;';
        div.innerHTML = `<input type="text" class="sd-array-input" data-qid="${qid}" style="flex:1;padding:8px;border:1px solid #000;font-size:14px;"><button type="button" onclick="SubscriptionsPage.removeArrayItem(this)" style="background:#dc3545;color:#fff;border:none;padding:0 10px;cursor:pointer;font-size:16px;">×</button>`;
        container.querySelector('.sd-array-items').appendChild(div);
    },

    removeArrayItem(btn) {
        const container = btn.closest('.sd-array-wrap');
        const items = container.querySelectorAll('.sd-array-item');
        if (items.length <= 1) return;
        btn.closest('.sd-array-item').remove();
        const remaining = container.querySelectorAll('.sd-array-item');
        if (remaining.length === 1) {
            const rmBtn = remaining[0].querySelector('button');
            if (rmBtn) rmBtn.remove();
        }
    },

    async saveAnswers() {
        if (!this.currentDetail) return;
        const subId = this.currentDetail.subscription.id;

        const answers = [];
        // text/textarea/number/date/select
        document.querySelectorAll('#sub-detail-body .sd-edit').forEach(el => {
            answers.push({ question_id: parseInt(el.dataset.qid), answer: el.value });
        });
        // radio
        document.querySelectorAll('#sub-detail-body .sd-edit-radio:checked').forEach(el => {
            answers.push({ question_id: parseInt(el.dataset.qid), answer: el.value });
        });
        // checkbox
        const checkMap = {};
        document.querySelectorAll('#sub-detail-body .sd-edit-check:checked').forEach(el => {
            const qid = el.dataset.qid;
            if (!checkMap[qid]) checkMap[qid] = [];
            checkMap[qid].push(el.value);
        });
        Object.entries(checkMap).forEach(([qid, vals]) => {
            answers.push({ question_id: parseInt(qid), answer: JSON.stringify(vals) });
        });
        // array - 最低件数チェック付き
        let arrayError = null;
        document.querySelectorAll('#sub-detail-body .sd-array-wrap').forEach(container => {
            const qid = container.dataset.qid;
            const minReq = parseInt(container.dataset.min) || 0;
            const vals = [];
            container.querySelectorAll('.sd-array-input').forEach(input => {
                if (input.value.trim()) vals.push(input.value.trim());
            });
            if (minReq > 0 && vals.length < minReq) {
                const label = container.closest('.form-group')?.querySelector('label')?.textContent || '項目';
                arrayError = `「${label.replace(' *', '')}」は${minReq}件以上入力してください`;
            }
            answers.push({ question_id: parseInt(qid), answer: JSON.stringify(vals) });
        });

        if (arrayError) {
            alert(arrayError);
            return;
        }

        try {
            await API.put(`/api/admin/subscriptions/${subId}/answers`, { answers });
            // 保存成功 → 最新データを再取得して閲覧モードに戻る
            const data = await API.get(`/api/admin/subscriptions/${subId}/detail`);
            this.currentDetail = data;
            this.editMode = false;
            this.renderDetail(data);
        } catch (e) {
            const msgEl = document.getElementById('sd-save-msg');
            if (msgEl) {
                msgEl.textContent = e.message;
                msgEl.style.color = '#dc3545';
            }
        }
    },

    closeDetail() {
        document.getElementById('sub-detail-modal').classList.remove('active');
        this.currentDetail = null;
        this.editMode = false;
    },

    fmtDate(iso) {
        if (!iso) return '-';
        return new Date(iso).toLocaleDateString('ja-JP');
    },

    esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    },
};
