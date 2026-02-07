/**
 * ダッシュボードUI
 */
const DashboardPage = {
    async render(container) {
        container.innerHTML = `
            <div class="content-header"><h1>ダッシュボード</h1></div>
            <div id="dash-content">読み込み中...</div>
        `;
        await this.load();
    },

    async load() {
        const el = document.getElementById('dash-content');
        try {
            const d = await API.get('/api/admin/dashboard');
            el.innerHTML = this.renderStats(d) + this.renderPlanBreakdown(d) + this.renderTodayDelivery(d) + this.renderRecent(d);
        } catch (e) {
            el.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    renderStats(d) {
        const items = [
            { label: '会員数', value: d.users.active, sub: `全${d.users.total}人` },
            { label: '加入者数', value: d.subscriptions.total_active, sub: `トライアル ${d.subscriptions.trialing}人` },
            { label: '月額売上', value: `&yen;${d.revenue.monthly.toLocaleString()}`, sub: '' },
            { label: '本日の配信', value: d.today.delivery_count, sub: `${d.today.sent}通送信` },
            { label: '本日 成功', value: d.today.success, sub: '', cls: 'dash-stat-success' },
            { label: '本日 失敗', value: d.today.fail, sub: '', cls: d.today.fail > 0 ? 'dash-stat-danger' : '' },
            { label: '本日 エラー', value: d.today.errors, sub: `警告 ${d.today.warnings}件`, cls: d.today.errors > 0 ? 'dash-stat-danger' : '' },
        ];
        return `
            <div class="dash-stats">
                ${items.map(i => `
                    <div class="dash-stat-card ${i.cls || ''}">
                        <div class="dash-stat-value">${i.value}</div>
                        <div class="dash-stat-label">${i.label}</div>
                        ${i.sub ? `<div class="dash-stat-sub">${i.sub}</div>` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    },

    renderPlanBreakdown(d) {
        if (d.plans_summary.length === 0) return '';
        const maxCount = Math.max(...d.plans_summary.map(p => p.count), 1);
        const rows = d.plans_summary.map(p => `
            <div class="dash-plan-row">
                <div class="dash-plan-name">${this.esc(p.name)}<span class="dash-plan-price">&yen;${p.price.toLocaleString()}/月</span></div>
                <div class="dash-plan-bar-wrap">
                    <div class="dash-plan-bar" style="width:${Math.round(p.count / maxCount * 100)}%"></div>
                </div>
                <div class="dash-plan-count">${p.count}人</div>
            </div>
        `).join('');
        return `
            <div class="card" style="margin-top:20px;">
                <h3 style="margin-bottom:15px;">プラン別加入者</h3>
                ${rows}
            </div>
        `;
    },

    renderTodayDelivery(d) {
        if (d.today.delivery_count === 0 && d.recent_deliveries.length === 0) return '';
        const total = d.today.success + d.today.fail;
        let barHtml = '';
        if (total > 0) {
            const successPct = Math.round(d.today.success / total * 100);
            barHtml = `
                <div class="dash-delivery-bar">
                    <div class="dash-delivery-bar-success" style="width:${successPct}%"></div>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:12px;color:#666;margin-top:4px;">
                    <span>成功 ${d.today.success}通 (${successPct}%)</span>
                    <span>失敗 ${d.today.fail}通</span>
                </div>
            `;
        }
        return `
            <div class="card" style="margin-top:20px;">
                <h3 style="margin-bottom:15px;">本日の配信状況</h3>
                ${barHtml || '<p style="color:#999;">本日の配信はまだありません</p>'}
            </div>
        `;
    },

    renderRecent(d) {
        let html = '';

        // 最近の配信
        if (d.recent_deliveries.length > 0) {
            const STATUS_LABELS = {success:'成功',partial_failed:'一部失敗',failed:'失敗',running:'実行中',stopped:'停止'};
            const TYPE_LABELS = {scheduled:'定時',manual:'手動',system:'システム'};
            html += `
                <div class="card" style="margin-top:20px;">
                    <div class="flex-between" style="margin-bottom:15px;">
                        <h3>最近の配信</h3>
                        <a href="#deliveries" style="font-size:13px;">すべて見る &rarr;</a>
                    </div>
                    <div class="table-container"><table>
                        <thead><tr><th>日時</th><th>プラン</th><th>種別</th><th>件名</th><th>結果</th></tr></thead>
                        <tbody>${d.recent_deliveries.map(r => {
                            const statusCls = r.status === 'success' ? 'badge-active' : (r.status === 'running' ? 'badge-warning' : 'badge-danger');
                            return `<tr>
                                <td style="white-space:nowrap;">${this.fmtDatetime(r.created_at)}</td>
                                <td>${this.esc(r.plan_name)}</td>
                                <td>${TYPE_LABELS[r.send_type] || r.send_type}</td>
                                <td>${this.esc((r.subject||'').substring(0,30))}</td>
                                <td><span class="badge ${statusCls}">${STATUS_LABELS[r.status]||r.status}</span> ${r.success}/${r.total}</td>
                            </tr>`;
                        }).join('')}</tbody>
                    </table></div>
                </div>
            `;
        }

        // 最近の登録
        if (d.recent_users.length > 0) {
            html += `
                <div class="card" style="margin-top:20px;">
                    <div class="flex-between" style="margin-bottom:15px;">
                        <h3>最近の新規会員</h3>
                        <a href="#users" style="font-size:13px;">すべて見る &rarr;</a>
                    </div>
                    <div class="table-container"><table>
                        <thead><tr><th>会員番号</th><th>名前</th><th>メール</th><th>登録日</th></tr></thead>
                        <tbody>${d.recent_users.map(u => `
                            <tr>
                                <td>${u.member_no}</td>
                                <td>${this.esc(u.name)}</td>
                                <td>${this.esc(u.email)}</td>
                                <td style="white-space:nowrap;">${this.fmtDatetime(u.created_at)}</td>
                            </tr>
                        `).join('')}</tbody>
                    </table></div>
                </div>
            `;
        }

        return html;
    },

    fmtDatetime(iso) {
        if (!iso) return '-';
        const d = new Date(iso);
        return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
    },

    esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    },
};
