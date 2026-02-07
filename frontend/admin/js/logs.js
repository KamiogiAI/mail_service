/**
 * システムログビューア
 */
const LogsPage = {
    async render(container) {
        container.innerHTML = `
            <div class="content-header"><h1>システムログ</h1></div>
            <div class="filters">
                <select id="log-level" style="padding:8px;border:1px solid #000;" onchange="LogsPage.load()">
                    <option value="">全レベル</option>
                    <option value="INFO">INFO</option>
                    <option value="WARNING">WARNING</option>
                    <option value="ERROR">ERROR</option>
                    <option value="CRITICAL">CRITICAL</option>
                </select>
                <input id="log-event" placeholder="event_type" style="padding:8px;border:1px solid #000;" onkeydown="if(event.key==='Enter')LogsPage.load()">
                <input id="log-start" type="date" style="padding:8px;border:1px solid #000;">
                <input id="log-end" type="date" style="padding:8px;border:1px solid #000;">
                <button class="btn btn-secondary" onclick="LogsPage.load()">検索</button>
                <button class="btn btn-danger" onclick="LogsPage.bulkDelete()">一括削除</button>
            </div>
            <div id="logs-list">読み込み中...</div>
        `;
        await this.load();
    },

    async load() {
        try {
            const params = new URLSearchParams({page: 1, per_page: 100});
            const level = document.getElementById('log-level')?.value;
            const eventType = document.getElementById('log-event')?.value;
            const start = document.getElementById('log-start')?.value;
            const end = document.getElementById('log-end')?.value;
            if (level) params.set('level', level);
            if (eventType) params.set('event_type', eventType);
            if (start) params.set('start_date', start);
            if (end) params.set('end_date', end);

            const data = await API.get(`/api/admin/logs?${params}`);
            const el = document.getElementById('logs-list');
            if (data.logs.length === 0) {
                el.innerHTML = '<p>ログがありません</p>';
                return;
            }

            const levelClass = {INFO:'',WARNING:'badge-warning',ERROR:'badge-danger',CRITICAL:'badge-danger'};
            el.innerHTML = `
                <p style="margin-bottom:10px;color:#666;">${data.total}件</p>
                <div class="table-container"><table>
                    <thead><tr><th>日時</th><th>レベル</th><th>イベント</th><th>プランID</th><th>会員番号</th><th>メッセージ</th></tr></thead>
                    <tbody>${data.logs.map(l => `
                        <tr>
                            <td style="white-space:nowrap;">${l.created_at ? new Date(l.created_at).toLocaleString('ja-JP') : '-'}</td>
                            <td><span class="badge ${levelClass[l.level]||''}">${l.level}</span></td>
                            <td>${l.event_type}</td>
                            <td>${l.plan_id || '-'}</td>
                            <td>${l.member_no_snapshot || '-'}</td>
                            <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;">${this.esc(l.message)}</td>
                        </tr>
                    `).join('')}</tbody>
                </table></div>
            `;
        } catch (e) {
            document.getElementById('logs-list').innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    async bulkDelete() {
        const endDate = document.getElementById('log-end')?.value;
        if (!endDate) { alert('削除対象の終了日を指定してください'); return; }
        if (!confirm(`${endDate}以前のログを全て削除しますか？`)) return;
        try {
            const res = await API.del(`/api/admin/logs/bulk-delete?before_date=${endDate}`);
            alert(res.message);
            this.load();
        } catch(e) { alert(e.message); }
    },

    esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; },
};
