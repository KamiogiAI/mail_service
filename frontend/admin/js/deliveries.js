/**
 * 配信履歴UI
 */
const DeliveriesPage = {
    currentFilter: '',
    currentDate: '',

    async render(container) {
        container.innerHTML = `
            <div class="content-header"><h1>配信履歴</h1></div>
            <div class="filters">
                <button class="filter-btn active" onclick="DeliveriesPage.setFilter(event,'')">全て</button>
                <button class="filter-btn" onclick="DeliveriesPage.setFilter(event,'scheduled')">定時</button>
                <button class="filter-btn" onclick="DeliveriesPage.setFilter(event,'manual')">手動</button>
                <button class="filter-btn" onclick="DeliveriesPage.setFilter(event,'system')">システム</button>
                <input id="del-date" type="date" style="padding:8px;border:1px solid #000;" onchange="DeliveriesPage.load()">
            </div>
            <div id="deliveries-list">読み込み中...</div>
        `;
        await this.load();
    },

    setFilter(e, f) {
        this.currentFilter = f;
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.load();
    },

    async load() {
        try {
            const params = new URLSearchParams({page: 1, per_page: 50});
            if (this.currentFilter) params.set('send_type', this.currentFilter);
            const dateVal = document.getElementById('del-date')?.value;
            if (dateVal) params.set('date', dateVal);
            const data = await API.get(`/api/admin/deliveries?${params}`);
            const el = document.getElementById('deliveries-list');
            if (!data.deliveries || data.deliveries.length === 0) {
                el.innerHTML = '<p>配信履歴がありません</p>';
                return;
            }
            el.innerHTML = `
                <div class="table-container"><table>
                    <thead><tr><th>日時</th><th>プラン</th><th>タイプ</th><th>送信数</th><th>成功</th><th>失敗</th><th>状態</th><th>操作</th></tr></thead>
                    <tbody>${data.deliveries.map(d => `
                        <tr>
                            <td>${d.created_at ? new Date(d.created_at).toLocaleString('ja-JP') : '-'}</td>
                            <td>${d.plan_name || '-'}</td>
                            <td>${d.send_type}</td>
                            <td>${d.total_count}</td>
                            <td>${d.success_count}</td>
                            <td>${d.fail_count}</td>
                            <td><span class="badge badge-${d.status==='success'?'active':d.status==='failed'?'danger':'warning'}">${d.status}</span></td>
                            <td><button class="btn btn-sm btn-danger" onclick="DeliveriesPage.del(${d.id})">削除</button></td>
                        </tr>
                    `).join('')}</tbody>
                </table></div>
            `;
        } catch (e) {
            document.getElementById('deliveries-list').innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    async del(id) {
        if (!confirm('この配信履歴を削除しますか？')) return;
        try { await API.del(`/api/admin/deliveries/${id}`); this.load(); } catch(e) { alert(e.message); }
    },

    esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; },
};
