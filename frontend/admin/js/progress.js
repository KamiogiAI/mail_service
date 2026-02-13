/**
 * 進捗管理UI (ダッシュボード + スケジュール + 進捗テーブル + 配信履歴 + エラー)
 */
const ProgressPage = {
    STATUS_CLASS: { '-1': 'badge-waiting', 0: 'badge-inactive', 1: 'badge-warning', 2: 'badge-active', 3: 'badge-danger' },
    STATUS_LABEL: { '-1': '待機中', 0: '未実行', 1: '実行中', 2: '完了', 3: 'エラー' },
    DELIVERY_STATUS_MAP: {
        running: ['badge-warning', '実行中'],
        success: ['badge-active', '成功'],
        partial_failed: ['badge-warning', '一部失敗'],
        failed: ['badge-danger', '失敗'],
        stopped: ['badge-inactive', '停止'],
    },
    manualSendPollingTimer: null,

    async render(container) {
        const today = new Date().toISOString().split('T')[0];
        container.innerHTML = `
            <div class="content-header" style="display:flex;justify-content:space-between;align-items:center;">
                <h1>進捗管理</h1>
                <div style="display:flex;gap:10px;align-items:center;">
                    <button class="btn btn-sm btn-secondary" onclick="ProgressPage.checkScheduler()">スケジューラー状態</button>
                    <span id="emergency-status"></span>
                </div>
            </div>
            <div id="progress-dashboard" class="card" style="margin-bottom:20px;">
                <div class="progress-dashboard">読み込み中...</div>
            </div>
            <div id="manual-send-progress" style="display:none;margin-bottom:20px;"></div>
            <div class="card" style="margin-bottom:20px;">
                <div class="card-header">
                    <h2>本日の進捗</h2>
                    <div style="display:flex;gap:10px;align-items:center;">
                        <input id="prog-date" type="date" value="${today}" style="padding:8px;border:1px solid #000;" onchange="ProgressPage.loadProgress()">
                        <button class="btn btn-sm btn-secondary" onclick="ProgressPage.loadProgress()">更新</button>
                    </div>
                </div>
                <div id="progress-table">読み込み中...</div>
            </div>
            <div class="card" style="margin-bottom:20px;">
                <div class="card-header"><h2>最近の配信履歴</h2></div>
                <div id="recent-deliveries">読み込み中...</div>
            </div>
            <div id="recent-errors-section" style="display:none;">
                <div class="card">
                    <div class="card-header"><h2>最近のエラー</h2></div>
                    <div id="recent-errors"></div>
                </div>
            </div>
            <div class="modal" id="progress-detail-modal">
                <div class="modal-content" style="max-width:900px;">
                    <div class="modal-header">
                        <h2 id="progress-detail-title">配信詳細</h2>
                        <button class="close-btn" onclick="ProgressPage.closeDetail()">&times;</button>
                    </div>
                    <div id="progress-detail-body">読み込み中...</div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="ProgressPage.closeDetail()">閉じる</button>
                    </div>
                </div>
            </div>
            <div class="modal" id="scheduler-status-modal">
                <div class="modal-content" style="max-width:800px;">
                    <div class="modal-header">
                        <h2>スケジューラー状態</h2>
                        <button class="close-btn" onclick="document.getElementById('scheduler-status-modal').classList.remove('active')">&times;</button>
                    </div>
                    <div id="scheduler-status-body">読み込み中...</div>
                    <div class="modal-footer">
                        <button class="btn btn-sm btn-secondary" onclick="ProgressPage.checkScheduler()">再チェック</button>
                        <button class="btn btn-secondary" onclick="document.getElementById('scheduler-status-modal').classList.remove('active')">閉じる</button>
                    </div>
                </div>
            </div>
        `;
        await Promise.all([
            this.loadDashboard(),
            this.loadProgress(),
            this.loadRecentDeliveries(),
            this.loadManualSendProgress(),
        ]);
    },

    // --- ダッシュボード ---
    async loadDashboard() {
        const el = document.getElementById('progress-dashboard');
        try {
            const d = await API.get('/api/admin/progress/dashboard');

            // 緊急停止ボタン
            const esEl = document.getElementById('emergency-status');
            esEl.innerHTML = d.emergency_stop
                ? `<span class="badge badge-danger">緊急停止中</span> <button class="btn btn-sm" onclick="ProgressPage.toggleStop(false)">解除</button>`
                : `<button class="btn btn-sm btn-danger" onclick="ProgressPage.toggleStop(true)">緊急停止</button>`;

            el.innerHTML = `
                <div class="progress-dashboard">
                    <div class="progress-stat-card">
                        <div class="progress-stat-value">${d.active_plans}</div>
                        <div class="progress-stat-label">有効プラン</div>
                    </div>
                    <div class="progress-stat-card ${d.running > 0 ? 'progress-stat-running' : ''}">
                        <div class="progress-stat-value">${d.running}</div>
                        <div class="progress-stat-label">実行中</div>
                    </div>
                    <div class="progress-stat-card progress-stat-success">
                        <div class="progress-stat-value">${d.completed}</div>
                        <div class="progress-stat-label">完了</div>
                    </div>
                    <div class="progress-stat-card ${d.errors > 0 ? 'progress-stat-error' : ''}">
                        <div class="progress-stat-value">${d.errors}</div>
                        <div class="progress-stat-label">エラー</div>
                    </div>
                    <div class="progress-stat-card">
                        <div class="progress-stat-value">${d.today_deliveries}</div>
                        <div class="progress-stat-label">本日配信</div>
                    </div>
                    <div class="progress-stat-card">
                        <div class="progress-stat-value">${d.today_total_sent}</div>
                        <div class="progress-stat-label">総送信数</div>
                    </div>
                    <div class="progress-stat-card progress-stat-success">
                        <div class="progress-stat-value">${d.today_success}</div>
                        <div class="progress-stat-label">成功</div>
                    </div>
                    <div class="progress-stat-card ${d.today_fail > 0 ? 'progress-stat-error' : ''}">
                        <div class="progress-stat-value">${d.today_fail}</div>
                        <div class="progress-stat-label">失敗</div>
                    </div>
                </div>
            `;

            // エラーセクション
            const errSection = document.getElementById('recent-errors-section');
            if (d.recent_errors && d.recent_errors.length > 0) {
                errSection.style.display = '';
                document.getElementById('recent-errors').innerHTML = `
                    <div class="table-container"><table>
                        <thead><tr><th>プラン名</th><th>エラー内容</th><th>発生日時</th></tr></thead>
                        <tbody>${d.recent_errors.map(e => `
                            <tr>
                                <td>${this.esc(e.plan_name)}</td>
                                <td style="max-width:400px;word-break:break-word;">${this.esc(e.error_message || '(詳細なし)')}</td>
                                <td>${e.created_at ? new Date(e.created_at).toLocaleString('ja-JP') : '-'}</td>
                            </tr>
                        `).join('')}</tbody>
                    </table></div>
                `;
            } else {
                errSection.style.display = 'none';
            }
        } catch (e) {
            el.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    // --- 進捗テーブル ---
    async loadProgress() {
        const el = document.getElementById('progress-table');
        try {
            const dateVal = document.getElementById('prog-date')?.value || '';
            const params = dateVal ? `?target_date=${dateVal}` : '';
            const data = await API.get(`/api/admin/progress${params}`);

            // 緊急停止
            const esEl = document.getElementById('emergency-status');
            esEl.innerHTML = data.emergency_stop
                ? `<span class="badge badge-danger">緊急停止中</span> <button class="btn btn-sm" onclick="ProgressPage.toggleStop(false)">解除</button>`
                : `<button class="btn btn-sm btn-danger" onclick="ProgressPage.toggleStop(true)">緊急停止</button>`;

            if (data.items.length === 0) {
                el.innerHTML = '<p style="color:#999;">進捗データがありません</p>';
                return;
            }

            el.innerHTML = `
                <div class="table-container"><table>
                    <thead><tr>
                        <th>プラン</th><th>配信タイプ</th><th>ステータス</th><th>処理状況</th><th>予定時刻</th><th>処理時間</th><th>最終更新</th><th>操作</th>
                    </tr></thead>
                    <tbody>${data.items.map(p => {
                        const total = p.total_items || 0;
                        const success = p.success_count || 0;
                        const fail = p.fail_count || 0;
                        const pct = total > 0 ? Math.round((success / total) * 100) : 0;
                        const failPct = total > 0 ? Math.round((fail / total) * 100) : 0;
                        const progressHtml = total > 0 ? `
                            <div style="display:flex;align-items:center;gap:8px;">
                                <div class="progress-bar-wrap">
                                    <div class="progress-bar-fill" style="width:${pct}%"></div>
                                    ${fail > 0 ? `<div class="progress-bar-error" style="width:${failPct}%;left:${pct}%"></div>` : ''}
                                </div>
                                <span style="font-size:12px;white-space:nowrap;">${success}/${total}${fail > 0 ? ` <span style="color:#dc3545;">(${fail}失敗)</span>` : ''}</span>
                            </div>
                        ` : '<span style="color:#999;font-size:12px;">-</span>';

                        // 処理時間
                        let durationHtml = '-';
                        if (p.duration_seconds !== null && p.duration_seconds !== undefined) {
                            if (p.duration_seconds < 60) {
                                durationHtml = `${p.duration_seconds}秒`;
                            } else {
                                const m = Math.floor(p.duration_seconds / 60);
                                const s = p.duration_seconds % 60;
                                durationHtml = `${m}分${s}秒`;
                            }
                            if (total > 0) {
                                const perItem = (p.duration_seconds / total).toFixed(1);
                                durationHtml += `<br><span style="font-size:11px;color:#666;">${perItem}秒/件</span>`;
                            }
                        } else if (p.status === 1 && p.delivery_started_at) {
                            // 実行中の場合は経過時間
                            const elapsed = Math.round((Date.now() - new Date(p.delivery_started_at).getTime()) / 1000);
                            if (elapsed < 60) {
                                durationHtml = `<span style="color:#e6a800;">${elapsed}秒経過</span>`;
                            } else {
                                durationHtml = `<span style="color:#e6a800;">${Math.floor(elapsed/60)}分${elapsed%60}秒経過</span>`;
                            }
                        }

                        return `
                            <tr>
                                <td>${this.esc(p.plan_name)}</td>
                                <td style="font-size:12px;">${this.esc(p.schedule_type || '-')}</td>
                                <td><span class="badge ${this.STATUS_CLASS[p.status] || ''} ${p.status === 1 ? 'badge-pulse' : ''}">${this.STATUS_LABEL[p.status] || '不明'}</span></td>
                                <td style="min-width:180px;">${progressHtml}</td>
                                <td>${p.schedule_time || '-'}</td>
                                <td>${durationHtml}</td>
                                <td style="font-size:12px;">${p.updated_at ? new Date(p.updated_at).toLocaleString('ja-JP') : '-'}</td>
                                <td>
                                    ${p.id !== null ? `<div class="action-btns">
                                        ${p.delivery_id ? `<button class="btn btn-sm btn-secondary" onclick="ProgressPage.showDetail(${p.id})">詳細</button>` : ''}
                                        ${p.fail_count > 0 ? `<button class="btn btn-sm btn-warning" onclick="ProgressPage.retryFailed(${p.id})">失敗分を再送</button>` : ''}
                                        <button class="btn btn-sm btn-secondary" onclick="ProgressPage.reset(${p.id})">リセット</button>
                                    </div>` : ''}
                                </td>
                            </tr>
                        `;
                    }).join('')}</tbody>
                </table></div>
            `;
        } catch (e) {
            el.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    // --- 最近の配信履歴 ---
    async loadRecentDeliveries() {
        const el = document.getElementById('recent-deliveries');
        try {
            const data = await API.get('/api/admin/deliveries?limit=10');
            if (!data.deliveries || data.deliveries.length === 0) {
                el.innerHTML = '<p style="color:#999;">配信履歴がありません</p>';
                return;
            }

            el.innerHTML = `
                <div class="table-container"><table>
                    <thead><tr>
                        <th>開始日時</th><th>プラン</th><th>タイプ</th><th>ステータス</th><th>成功</th><th>失敗</th><th>操作</th>
                    </tr></thead>
                    <tbody>${data.deliveries.map(d => {
                        const [sClass, sLabel] = this.DELIVERY_STATUS_MAP[d.status] || ['badge-inactive', d.status];
                        return `
                            <tr>
                                <td>${d.started_at ? new Date(d.started_at).toLocaleString('ja-JP') : '-'}</td>
                                <td>${this.esc(d.plan_name)}</td>
                                <td><span style="font-size:12px;">${d.send_type}</span></td>
                                <td><span class="badge ${sClass}">${sLabel}</span></td>
                                <td>${d.success_count}</td>
                                <td>${d.fail_count > 0 ? `<span style="color:#dc3545;font-weight:600;">${d.fail_count}</span>` : '0'}</td>
                                <td><button class="btn btn-sm btn-secondary" onclick="ProgressPage.showDeliveryDetail(${d.id})">詳細</button></td>
                            </tr>
                        `;
                    }).join('')}</tbody>
                </table></div>
            `;
        } catch (e) {
            el.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    // --- 実行中の手動送信進捗 ---
    async loadManualSendProgress() {
        const container = document.getElementById('manual-send-progress');
        if (!container) return;

        try {
            const response = await API.get('/api/admin/deliveries?limit=5');
            const runningManual = response.deliveries.filter(d => d.send_type === 'manual' && d.status === 'running');

            if (runningManual.length === 0) {
                container.style.display = 'none';
                if (this.manualSendPollingTimer) {
                    clearInterval(this.manualSendPollingTimer);
                    this.manualSendPollingTimer = null;
                }
                return;
            }

            container.style.display = 'block';
            let html = '';

            for (const d of runningManual) {
                const total = d.total_count || 0;
                const success = d.success_count || 0;
                const fail = d.fail_count || 0;
                const progress = success + fail;
                const percent = total > 0 ? Math.round((progress / total) * 100) : 0;

                html += `
                    <div class="card" style="border-left:4px solid #e6a800;">
                        <div class="card-header">
                            <h2>📤 手動送信 実行中</h2>
                            <span class="badge badge-warning badge-pulse">実行中</span>
                        </div>
                        <div style="padding:15px;">
                            <div style="margin-bottom:10px;">
                                <strong>件名:</strong> ${this.esc(d.subject || '-')}
                            </div>
                            <div style="margin-bottom:15px;">
                                <div style="display:flex;align-items:center;gap:10px;">
                                    <div style="flex:1;">
                                        <div class="progress-bar-wrap" style="height:20px;">
                                            <div class="progress-bar-fill" style="width:${percent}%;height:100%;"></div>
                                        </div>
                                    </div>
                                    <span style="font-weight:600;white-space:nowrap;">${progress} / ${total} (${percent}%)</span>
                                </div>
                                <div style="margin-top:8px;font-size:13px;">
                                    <span style="color:#28a745;">✓ 成功: ${success}</span>
                                    ${fail > 0 ? `<span style="color:#dc3545;margin-left:15px;">✗ 失敗: ${fail}</span>` : ''}
                                </div>
                            </div>
                            <button class="btn btn-sm btn-secondary" onclick="ProgressPage.showManualSendDetail(${d.id})">送信先詳細</button>
                        </div>
                    </div>
                `;
            }

            container.innerHTML = html;

            // ポーリング開始（まだ開始していない場合）
            if (!this.manualSendPollingTimer) {
                this.manualSendPollingTimer = setInterval(() => {
                    this.loadManualSendProgress();
                    this.loadDashboard();
                }, 3000);
            }
        } catch (e) {
            console.error('Manual send progress error:', e);
        }
    },

    // --- 手動送信詳細モーダル ---
    async showManualSendDetail(deliveryId) {
        const modal = document.getElementById('progress-detail-modal');
        const body = document.getElementById('progress-detail-body');
        modal.classList.add('active');
        body.innerHTML = '<p>読み込み中...</p>';

        try {
            const data = await API.get(`/api/admin/deliveries/${deliveryId}/items`);
            document.getElementById('progress-detail-title').textContent = '手動送信 - 送信先詳細';

            const d = data.delivery;
            const total = d.total_count || 0;
            const success = d.success_count || 0;
            const fail = d.fail_count || 0;
            const percent = total > 0 ? Math.round(((success + fail) / total) * 100) : 0;

            let html = `
                <div style="margin-bottom:20px;">
                    <div class="subs-summary" style="grid-template-columns:repeat(auto-fill,minmax(100px,1fr));">
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">ステータス</div>
                            <div style="margin-top:4px;"><span class="badge ${d.status === 'running' ? 'badge-warning badge-pulse' : 'badge-active'}">${d.status === 'running' ? '実行中' : '完了'}</span></div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">進捗</div>
                            <div class="subs-summary-value" style="font-size:18px;">${percent}%</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">総数</div>
                            <div class="subs-summary-value" style="font-size:18px;">${total}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">成功</div>
                            <div class="subs-summary-value" style="font-size:18px;color:#28a745;">${success}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">失敗</div>
                            <div class="subs-summary-value" style="font-size:18px;color:${fail > 0 ? '#dc3545' : '#000'};">${fail}</div>
                        </div>
                    </div>
                </div>
            `;

            if (data.items && data.items.length > 0) {
                const itemStatusMap = { 0: ['badge-inactive', '待機'], 1: ['badge-warning', '実行中'], 2: ['badge-active', '成功'], 3: ['badge-danger', '失敗'] };
                html += `
                    <div class="table-container"><table>
                        <thead><tr><th>会員番号</th><th>名前</th><th>メール</th><th>ステータス</th><th>送信日時</th></tr></thead>
                        <tbody>${data.items.map(item => {
                            const [iClass, iLabel] = itemStatusMap[item.status] || ['badge-inactive', '不明'];
                            return `
                                <tr>
                                    <td>${this.esc(item.member_no)}</td>
                                    <td>${this.esc(item.user_name)}</td>
                                    <td>${this.esc(item.email)}</td>
                                    <td><span class="badge ${iClass}">${iLabel}</span></td>
                                    <td>${item.sent_at ? new Date(item.sent_at).toLocaleString('ja-JP') : '-'}</td>
                                </tr>
                            `;
                        }).join('')}</tbody>
                    </table></div>
                `;
            } else {
                html += '<p style="color:#999;">送信先がありません</p>';
            }

            body.innerHTML = html;
        } catch (e) {
            body.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    // --- 詳細モーダル (進捗IDから) ---
    async showDetail(progressId) {
        const modal = document.getElementById('progress-detail-modal');
        const body = document.getElementById('progress-detail-body');
        modal.classList.add('active');
        body.innerHTML = '<p>読み込み中...</p>';

        try {
            const data = await API.get(`/api/admin/progress/${progressId}/detail`);
            this.renderDetailModal(data);
        } catch (e) {
            body.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    // --- 詳細モーダル (配信IDから直接) ---
    async showDeliveryDetail(deliveryId) {
        const modal = document.getElementById('progress-detail-modal');
        const body = document.getElementById('progress-detail-body');
        modal.classList.add('active');
        body.innerHTML = '<p>読み込み中...</p>';

        try {
            const dateVal = document.getElementById('prog-date')?.value || '';
            const params = dateVal ? `?target_date=${dateVal}` : '';
            const progData = await API.get(`/api/admin/progress${params}`);
            const match = progData.items.find(p => p.delivery_id === deliveryId);
            if (match) {
                const data = await API.get(`/api/admin/progress/${match.id}/detail`);
                this.renderDetailModal(data);
            } else {
                body.innerHTML = '<p style="color:#999;">この配信に対応する進捗データが見つかりませんでした</p>';
            }
        } catch (e) {
            body.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    renderDetailModal(data) {
        const body = document.getElementById('progress-detail-body');
        document.getElementById('progress-detail-title').textContent =
            `${data.plan_name} - 配信詳細`;

        let html = '';

        if (data.delivery) {
            const d = data.delivery;
            const [sClass, sLabel] = this.DELIVERY_STATUS_MAP[d.status] || ['badge-inactive', d.status];

            // 処理時間計算
            let durationStr = '-';
            if (d.started_at && d.completed_at) {
                const sec = Math.round((new Date(d.completed_at) - new Date(d.started_at)) / 1000);
                if (sec < 60) {
                    durationStr = `${sec}秒`;
                } else {
                    durationStr = `${Math.floor(sec / 60)}分${sec % 60}秒`;
                }
                if (d.total_count > 0) {
                    durationStr += ` (${(sec / d.total_count).toFixed(1)}秒/件)`;
                }
            }

            // 手動送信の場合のみ件名を表示
            const subjectHtml = d.send_type === 'manual' ? `
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">件名</div>
                            <div class="subs-summary-value" style="font-size:12px;">${this.esc(d.subject || '-')}</div>
                        </div>` : '';

            html += `
                <div style="margin-bottom:20px;">
                    <div class="subs-summary" style="grid-template-columns:repeat(auto-fill,minmax(130px,1fr));">
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">ステータス</div>
                            <div style="margin-top:4px;"><span class="badge ${sClass}">${sLabel}</span></div>
                        </div>
                        ${subjectHtml}
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">総数</div>
                            <div class="subs-summary-value" style="font-size:18px;">${d.total_count}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">成功</div>
                            <div class="subs-summary-value" style="font-size:18px;color:#28a745;">${d.success_count}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">失敗</div>
                            <div class="subs-summary-value" style="font-size:18px;color:${d.fail_count > 0 ? '#dc3545' : '#000'};">${d.fail_count}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">処理時間</div>
                            <div class="subs-summary-value" style="font-size:13px;">${durationStr}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">開始</div>
                            <div class="subs-summary-value" style="font-size:12px;">${d.started_at ? new Date(d.started_at).toLocaleString('ja-JP') : '-'}</div>
                        </div>
                        <div class="subs-summary-item">
                            <div class="subs-summary-label">完了</div>
                            <div class="subs-summary-value" style="font-size:12px;">${d.completed_at ? new Date(d.completed_at).toLocaleString('ja-JP') : '-'}</div>
                        </div>
                    </div>
                </div>
            `;
        }

        // ユーザー別結果テーブル
        if (data.items && data.items.length > 0) {
            const itemStatusMap = { 0: ['badge-inactive', '未実行'], 1: ['badge-warning', '実行中'], 2: ['badge-active', '完了'], 3: ['badge-danger', 'エラー'] };
            html += `
                <div class="table-container"><table>
                    <thead><tr><th>会員番号</th><th>名前</th><th>メール</th><th>ステータス</th><th>送信日時</th><th>エラー</th></tr></thead>
                    <tbody>${data.items.map(item => {
                        const [iClass, iLabel] = itemStatusMap[item.status] || ['badge-inactive', '不明'];
                        return `
                            <tr>
                                <td>${this.esc(item.member_no)}</td>
                                <td>${this.esc(item.user_name)}</td>
                                <td>${this.esc(item.email)}</td>
                                <td><span class="badge ${iClass}">${iLabel}</span></td>
                                <td>${item.sent_at ? new Date(item.sent_at).toLocaleString('ja-JP') : '-'}</td>
                                <td style="max-width:200px;word-break:break-word;color:#dc3545;">${this.esc(item.error_message || '')}</td>
                            </tr>
                        `;
                    }).join('')}</tbody>
                </table></div>
            `;
        } else {
            html += '<p style="color:#999;">配信アイテムがありません</p>';
        }

        body.innerHTML = html;
    },

    closeDetail() {
        document.getElementById('progress-detail-modal').classList.remove('active');
    },

    async reset(id) {
        try {
            await API.post(`/api/admin/progress/${id}/reset`);
            this.loadProgress();
        } catch (e) {
            alert(e.message);
        }
    },

    async retryFailed(id) {
        if (!confirm('失敗したユーザーに再送しますか？（最大3回リトライします）')) return;
        try {
            const result = await API.post(`/api/admin/progress/${id}/retry-failed`);
            alert(`再送完了: ${result.success}件成功 / ${result.failed}件失敗`);
            this.loadProgress();
            this.loadRecentDeliveries();
        } catch (e) {
            alert(e.message);
        }
    },

    async toggleStop(active) {
        if (active && !confirm('緊急停止を有効にしますか？全ての送信が一時停止されます。')) return;
        try {
            await API.post(`/api/admin/progress/emergency-stop?active=${active}`);
            this.loadProgress();
            this.loadDashboard();
        } catch (e) {
            alert(e.message);
        }
    },

    // --- スケジューラー状態チェック ---
    async checkScheduler() {
        const modal = document.getElementById('scheduler-status-modal');
        const body = document.getElementById('scheduler-status-body');
        modal.classList.add('active');
        body.innerHTML = '<p>チェック中...</p>';

        try {
            const d = await API.get('/api/admin/progress/scheduler-status');

            // ヘッダー: 現在時刻 + スケジューラー状態
            const aliveClass = d.scheduler_alive ? 'badge-active' : 'badge-danger';
            const aliveLabel = d.scheduler_alive ? '稼働中' : '停止';
            const esClass = d.emergency_stop ? 'badge-danger' : 'badge-active';
            const esLabel = d.emergency_stop ? '緊急停止中' : '正常';

            let html = `
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-bottom:20px;">
                    <div style="border:1px solid #ddd;padding:12px;text-align:center;">
                        <div style="font-size:11px;color:#666;margin-bottom:4px;">現在時刻</div>
                        <div style="font-size:16px;font-weight:700;">${this.esc(d.current_time)}</div>
                        <div style="font-size:12px;color:#666;">${this.esc(d.current_weekday)}</div>
                    </div>
                    <div style="border:1px solid #ddd;padding:12px;text-align:center;">
                        <div style="font-size:11px;color:#666;margin-bottom:4px;">スケジューラー</div>
                        <div style="margin-top:4px;"><span class="badge ${aliveClass}">${aliveLabel}</span></div>
                        ${d.last_heartbeat ? `<div style="font-size:10px;color:#999;margin-top:4px;">最終応答: ${this.esc(d.last_heartbeat.split('T')[1]?.substring(0,8) || d.last_heartbeat)}</div>` : ''}
                    </div>
                    <div style="border:1px solid #ddd;padding:12px;text-align:center;">
                        <div style="font-size:11px;color:#666;margin-bottom:4px;">緊急停止</div>
                        <div style="margin-top:4px;"><span class="badge ${esClass}">${esLabel}</span></div>
                    </div>
                </div>
            `;

            // プラン別状態テーブル
            if (d.plans && d.plans.length > 0) {
                html += `
                    <div class="table-container"><table>
                        <thead><tr>
                            <th>プラン名</th>
                            <th>配信タイプ</th>
                            <th>配信時刻</th>
                            <th>本日実行</th>
                            <th>配信状態</th>
                        </tr></thead>
                        <tbody>${d.plans.map(p => {
                            // 本日実行判定
                            const targetBadge = p.is_today_target
                                ? '<span class="badge badge-active">はい</span>'
                                : '<span class="badge badge-inactive">いいえ</span>';

                            // 配信状態
                            let statusHtml = '';
                            if (p.sent_today && p.delivery_info) {
                                const di = p.delivery_info;
                                statusHtml = `<span class="badge badge-active">送信済</span>
                                    <span style="font-size:11px;margin-left:4px;">${di.success_count}成功`;
                                if (di.fail_count > 0) statusHtml += ` / <span style="color:#dc3545;">${di.fail_count}失敗</span>`;
                                statusHtml += `</span>`;
                            } else if (p.today_status !== null) {
                                const cls = this.STATUS_CLASS[p.today_status] || '';
                                statusHtml = `<span class="badge ${cls}">${this.esc(p.today_status_label)}</span>`;
                            } else {
                                statusHtml = '<span style="color:#999;">-</span>';
                            }

                            return `
                                <tr>
                                    <td>${this.esc(p.plan_name)}</td>
                                    <td>${this.esc(p.schedule_type)}</td>
                                    <td>${this.esc(p.send_time)}</td>
                                    <td>
                                        ${targetBadge}
                                        <div style="font-size:10px;color:#666;margin-top:2px;">${this.esc(p.target_reason)}</div>
                                    </td>
                                    <td>${statusHtml}</td>
                                </tr>
                            `;
                        }).join('')}</tbody>
                    </table></div>
                `;
            } else {
                html += '<p style="color:#999;">有効なプランがありません</p>';
            }

            body.innerHTML = html;
        } catch (e) {
            body.innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    esc(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    },
};
