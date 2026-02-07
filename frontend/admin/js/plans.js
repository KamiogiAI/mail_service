/**
 * プラン管理UI + 質問ビルダー
 */
const PlansPage = {
    async render(container) {
        container.innerHTML = `
            <div class="content-header flex-between">
                <h1>プラン管理</h1>
                <button class="btn" onclick="PlansPage.showCreateModal()">新規プラン</button>
            </div>
            <div id="plans-list" class="loading">読み込み中...</div>
            ${this.modalHTML()}
        `;
        await this.loadPlans();
    },

    async loadPlans() {
        try {
            const plans = await API.get('/api/admin/plans');
            const el = document.getElementById('plans-list');
            el.classList.remove('loading');
            if (plans.length === 0) {
                el.innerHTML = '<p>プランがありません</p>';
                return;
            }
            el.innerHTML = `
                <div class="table-container">
                <table>
                    <thead><tr>
                        <th>プラン名</th><th>料金</th><th>配信タイプ</th><th>配信時刻</th>
                        <th>モデル</th><th>加入者</th><th>状態</th><th>操作</th>
                    </tr></thead>
                    <tbody>
                    ${plans.map(p => `
                        <tr>
                            <td>${this.esc(p.name)}</td>
                            <td>¥${p.price.toLocaleString()}/月</td>
                            <td>${p.schedule_type}</td>
                            <td>${p.send_time || '-'}</td>
                            <td>${p.model}</td>
                            <td>${p.subscriber_count}</td>
                            <td><span class="badge ${p.is_active ? 'badge-active' : 'badge-inactive'}">${p.is_active ? '有効' : '無効'}</span></td>
                            <td class="action-btns">
                                <button class="btn btn-sm btn-secondary" onclick="PlansPage.showEditModal(${p.id})">編集</button>
                                <button class="btn btn-sm btn-danger" onclick="PlansPage.deletePlan(${p.id}, '${this.esc(p.name)}')">削除</button>
                            </td>
                        </tr>
                    `).join('')}
                    </tbody>
                </table>
                </div>
            `;
        } catch (e) {
            document.getElementById('plans-list').innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    modalHTML() {
        return `
        <div class="modal" id="plan-modal">
            <div class="modal-content" style="max-width:800px;">
                <div class="modal-header">
                    <h2 id="plan-modal-title">プラン作成</h2>
                    <button class="close-btn" onclick="PlansPage.closeModal()">&times;</button>
                </div>
                <div class="tabs">
                    <button class="tab-btn active" onclick="PlansPage.switchTab(event,'basic')">基本設定</button>
                    <button class="tab-btn" onclick="PlansPage.switchTab(event,'questions')">質問項目</button>
                    <button class="tab-btn" onclick="PlansPage.switchTab(event,'summary')">あらすじ</button>
                    <button class="tab-btn" onclick="PlansPage.switchTab(event,'external')">外部データ</button>
                </div>
                <div id="tab-basic" class="tab-content active">
                    <div class="form-group"><label>プラン名</label><input id="p-name" type="text"></div>
                    <div class="form-group"><label>説明</label><textarea id="p-desc"></textarea></div>
                    <div class="form-group"><label>月額料金 (円)</label><input id="p-price" type="number" min="0"></div>
                    <div class="form-group">
                        <label>配信タイプ</label>
                        <select id="p-schedule-type" onchange="PlansPage.onScheduleTypeChange()">
                            <option value="daily">毎日</option>
                            <option value="weekday">曜日指定</option>
                            <option value="sheets">Sheets日付</option>
                        </select>
                    </div>
                    <div class="form-group"><label>配信時刻 (HH:MM)</label><input id="p-send-time" type="time"></div>
                    <div class="form-group" id="weekday-group" style="display:none;">
                        <label>配信曜日</label>
                        <div class="weekday-checks">
                            <label><input type="checkbox" value="0" class="weekday-cb">月</label>
                            <label><input type="checkbox" value="1" class="weekday-cb">火</label>
                            <label><input type="checkbox" value="2" class="weekday-cb">水</label>
                            <label><input type="checkbox" value="3" class="weekday-cb">木</label>
                            <label><input type="checkbox" value="4" class="weekday-cb">金</label>
                            <label><input type="checkbox" value="5" class="weekday-cb">土</label>
                            <label><input type="checkbox" value="6" class="weekday-cb">日</label>
                        </div>
                    </div>
                    <div class="form-group" id="sheets-group" style="display:none;">
                        <label>Google Sheets ID</label>
                        <input id="p-sheets-id" type="text" placeholder="スプレッドシートIDを入力">
                        <small>URLの /d/ と /edit の間の文字列</small>
                        <div id="sheets-firebase-msg" style="margin-top:8px;"></div>
                        <button type="button" class="btn btn-sm btn-secondary" style="margin-top:8px;" onclick="PlansPage.testSheets()">動作チェック</button>
                        <div id="sheets-test-result" style="margin-top:8px;"></div>
                    </div>
                    <div class="form-group">
                        <label>GPTモデル</label>
                        <select id="p-model">
                            <option value="gpt-4o-mini">gpt-4o-mini</option>
                            <option value="gpt-4o">gpt-4o</option>
                            <option value="gpt-4.1-mini">gpt-4.1-mini</option>
                            <option value="gpt-4.1">gpt-4.1</option>
                            <option value="gpt-5">gpt-5</option>
                        </select>
                    </div>
                    <div class="form-group"><label>ベースプロンプト</label><textarea id="p-system-prompt" rows="3" placeholder="GPTに与える役割・形式指定"></textarea></div>
                    <div class="form-group"><label>個別指示 (プロンプト)</label><textarea id="p-prompt" rows="6" placeholder="変数: {name} {var_name} {external_data}"></textarea></div>
                    <div class="form-group"><label><input type="checkbox" id="p-trial" checked>初月無料トライアルを有効にする</label></div>
                    <div class="form-group"><label><input type="checkbox" id="p-batch">まとめて送信 (batch_send)</label></div>
                    <div class="form-group"><label><input type="checkbox" id="p-active" checked>有効</label></div>
                </div>
                <div id="tab-questions" class="tab-content">
                    <div id="questions-container"></div>
                    <button class="btn btn-secondary mt-10" onclick="PlansPage.addQuestion()">+ 質問追加</button>
                </div>
                <div id="tab-summary" class="tab-content">
                    <div class="form-group"><label><input type="checkbox" id="s-enabled">あらすじ機能を有効にする</label></div>
                    <div id="summary-fields" style="display:none;">
                        <div class="form-group"><label>あらすじプロンプト</label><textarea id="s-prompt" rows="4"></textarea></div>
                        <div class="form-group"><label>目標文字数</label><input id="s-length" type="number" value="200"></div>
                        <div class="form-group"><label>保持件数</label><input id="s-max-keep" type="number" value="10"></div>
                        <div class="form-group"><label>注入件数</label><input id="s-inject" type="number" value="3"></div>
                    </div>
                </div>
                <div id="tab-external" class="tab-content">
                    <div class="form-group"><label>Firestoreパス</label><input id="e-path" type="text" placeholder="collection/doc/~"></div>
                    <div class="form-group">
                        <label>Firebase Key JSON</label>
                        <input type="file" id="e-key-file" accept=".json" onchange="PlansPage.onFirebaseFileSelected()">
                        <span id="e-key-status" style="margin-left:8px;color:#666;"></span>
                    </div>
                    <button type="button" class="btn btn-sm btn-secondary" onclick="PlansPage.testExternalData()">動作チェック</button>
                    <div id="external-test-result" style="margin-top:8px;"></div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="PlansPage.closeModal()">キャンセル</button>
                    <button class="btn" id="plan-save-btn" onclick="PlansPage.save()">保存</button>
                </div>
                <div id="plan-modal-error" class="error-message"></div>
            </div>
        </div>`;
    },

    editingId: null,
    questions: [],
    firebaseKeyJson: null,

    async onScheduleTypeChange() {
        const type = document.getElementById('p-schedule-type').value;
        document.getElementById('weekday-group').style.display = type === 'weekday' ? '' : 'none';
        document.getElementById('sheets-group').style.display = type === 'sheets' ? '' : 'none';

        if (type === 'sheets') {
            const msgEl = document.getElementById('sheets-firebase-msg');
            try {
                const settings = await API.get('/api/admin/settings');
                if (settings.firebase_client_email) {
                    msgEl.innerHTML = `<span style="color:#0d6efd;">スプレッドシートを <strong>${this.esc(settings.firebase_client_email)}</strong> に共有してください</span>`;
                } else {
                    msgEl.innerHTML = '<span style="color:#dc3545;">Firebase Key JSONが未設定です。<a href="#" onclick="Router.navigate(\'settings\');return false;">設定画面</a>から登録してください</span>';
                }
            } catch {
                msgEl.innerHTML = '';
            }
        }
    },

    onSummaryToggle() {
        const enabled = document.getElementById('s-enabled').checked;
        document.getElementById('summary-fields').style.display = enabled ? '' : 'none';
    },

    onFirebaseFileSelected() {
        const file = document.getElementById('e-key-file').files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (e) => {
            PlansPage.firebaseKeyJson = e.target.result;
            document.getElementById('e-key-status').textContent = file.name + ' 読み込み済み';
        };
        reader.readAsText(file);
    },

    switchTab(e, tab) {
        document.querySelectorAll('#plan-modal .tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('#plan-modal .tab-content').forEach(c => c.classList.remove('active'));
        e.target.classList.add('active');
        document.getElementById('tab-' + tab).classList.add('active');
    },

    showCreateModal() {
        this.editingId = null;
        this.questions = [];
        this.firebaseKeyJson = null;
        document.getElementById('plan-modal-title').textContent = 'プラン作成';
        this.clearForm();
        this.renderQuestions();
        this.onScheduleTypeChange();
        this.onSummaryToggle();
        document.getElementById('plan-modal').classList.add('active');
    },

    async showEditModal(id) {
        try {
            const plan = await API.get(`/api/admin/plans/${id}`);
            this.editingId = id;
            this.firebaseKeyJson = null;
            document.getElementById('plan-modal-title').textContent = 'プラン編集';
            document.getElementById('p-name').value = plan.name || '';
            document.getElementById('p-desc').value = plan.description || '';
            document.getElementById('p-price').value = plan.price;
            document.getElementById('p-schedule-type').value = plan.schedule_type;
            document.getElementById('p-send-time').value = plan.send_time || '';
            document.getElementById('p-sheets-id').value = plan.sheets_id || '';
            document.getElementById('p-model').value = plan.model;
            document.getElementById('p-system-prompt').value = plan.system_prompt || '';
            document.getElementById('p-prompt').value = plan.prompt || '';
            document.getElementById('p-trial').checked = plan.trial_enabled !== false;
            document.getElementById('p-batch').checked = plan.batch_send_enabled;
            document.getElementById('p-active').checked = plan.is_active;

            // 曜日チェックボックス復元
            document.querySelectorAll('.weekday-cb').forEach(cb => {
                cb.checked = (plan.schedule_weekdays || []).includes(parseInt(cb.value));
            });

            this.onScheduleTypeChange();

            this.questions = plan.questions || [];
            this.renderQuestions();

            // あらすじ設定
            const hasSummary = !!plan.summary_setting;
            document.getElementById('s-enabled').checked = hasSummary;
            if (hasSummary) {
                document.getElementById('s-prompt').value = plan.summary_setting.summary_prompt || '';
                document.getElementById('s-length').value = plan.summary_setting.summary_length_target;
                document.getElementById('s-max-keep').value = plan.summary_setting.summary_max_keep;
                document.getElementById('s-inject').value = plan.summary_setting.summary_inject_count;
            }
            this.onSummaryToggle();

            // 外部データ
            if (plan.external_data_setting) {
                document.getElementById('e-path').value = plan.external_data_setting.external_data_path || '';
                document.getElementById('e-key-status').textContent = plan.external_data_setting.has_firebase_key ? '設定済み' : '';
            }

            // テスト結果クリア
            document.getElementById('external-test-result').innerHTML = '';
            document.getElementById('sheets-test-result').innerHTML = '';

            document.getElementById('plan-modal').classList.add('active');
        } catch (e) {
            alert(e.message);
        }
    },

    closeModal() {
        document.getElementById('plan-modal').classList.remove('active');
        document.getElementById('plan-modal-error').textContent = '';
    },

    clearForm() {
        ['p-name','p-desc','p-price','p-send-time','p-sheets-id','p-system-prompt','p-prompt','s-prompt','e-path'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        document.getElementById('p-price').value = '0';
        document.getElementById('p-schedule-type').value = 'daily';
        document.getElementById('p-model').value = 'gpt-4o-mini';
        document.getElementById('p-trial').checked = true;
        document.getElementById('p-batch').checked = false;
        document.getElementById('p-active').checked = true;
        document.getElementById('s-enabled').checked = false;
        document.getElementById('s-length').value = '200';
        document.getElementById('s-max-keep').value = '10';
        document.getElementById('s-inject').value = '3';
        document.getElementById('e-key-file').value = '';
        document.getElementById('e-key-status').textContent = '';
        document.getElementById('external-test-result').innerHTML = '';
        document.getElementById('sheets-test-result').innerHTML = '';
        document.querySelectorAll('.weekday-cb').forEach(cb => cb.checked = false);
    },

    TYPE_LABELS: {
        text: 'テキスト (1行)',
        textarea: 'テキスト (複数行)',
        number: '数値',
        date: '日付',
        select: 'ドロップダウン',
        radio: 'ラジオボタン',
        checkbox: 'チェックボックス',
        array: '配列 (複数入力)',
    },

    NEEDS_OPTIONS: ['select', 'radio', 'checkbox'],

    addQuestion() {
        this.questions.push({
            var_name: '', label: '', question_type: 'text',
            options: null, array_max: null, array_min: null, is_required: true, track_changes: false, sort_order: this.questions.length
        });
        this.renderQuestions();
    },

    removeQuestion(idx) {
        this.questions.splice(idx, 1);
        this.renderQuestions();
    },

    onQuestionTypeChange(idx, value) {
        this.questions[idx].question_type = value;
        if (!this.NEEDS_OPTIONS.includes(value)) {
            this.questions[idx].options = null;
        }
        if (value !== 'array') {
            this.questions[idx].array_max = null;
            this.questions[idx].array_min = null;
        }
        this.renderQuestions();
    },

    addOption(idx) {
        if (!this.questions[idx].options) this.questions[idx].options = [];
        this.questions[idx].options.push('');
        this.renderQuestions();
    },

    removeOption(idx, optIdx) {
        this.questions[idx].options.splice(optIdx, 1);
        if (this.questions[idx].options.length === 0) this.questions[idx].options = null;
        this.renderQuestions();
    },

    updateOption(idx, optIdx, value) {
        this.questions[idx].options[optIdx] = value;
    },

    renderQuestions() {
        const c = document.getElementById('questions-container');
        if (!c) return;
        const T = this.TYPE_LABELS;
        c.innerHTML = this.questions.map((q, i) => {
            const needsOptions = this.NEEDS_OPTIONS.includes(q.question_type);
            const isArray = q.question_type === 'array';

            let optionsHtml = '';
            if (needsOptions) {
                const items = (q.options || []).map((opt, oi) => `
                    <div class="option-row">
                        <input value="${this.esc(opt)}" onchange="PlansPage.updateOption(${i},${oi},this.value)" placeholder="選択肢${oi + 1}">
                        <button class="btn btn-sm btn-danger" onclick="PlansPage.removeOption(${i},${oi})">×</button>
                    </div>
                `).join('');
                optionsHtml = `
                    <div class="form-group">
                        <label>選択肢</label>
                        <div class="options-list">${items}</div>
                        <button class="btn btn-sm btn-secondary mt-10" onclick="PlansPage.addOption(${i})">+ 選択肢追加</button>
                    </div>
                `;
            }

            let arrayHtml = '';
            if (isArray) {
                arrayHtml = `
                    <div class="form-row">
                        <div class="form-group"><label>最低必須件数</label><input type="number" min="0" value="${q.array_min||''}" onchange="PlansPage.questions[${i}].array_min=this.value?parseInt(this.value):null" placeholder="0"></div>
                        <div class="form-group"><label>最大件数</label><input type="number" min="1" value="${q.array_max||''}" onchange="PlansPage.questions[${i}].array_max=this.value?parseInt(this.value):null" placeholder="制限なし"></div>
                    </div>
                `;
            }

            return `
            <div class="question-item">
                <button class="btn btn-sm btn-danger remove-btn" onclick="PlansPage.removeQuestion(${i})">×</button>
                <div class="form-row">
                    <div class="form-group"><label>変数名</label><input value="${this.esc(q.var_name)}" onchange="PlansPage.questions[${i}].var_name=this.value" placeholder="prompt内の{変数名}"></div>
                    <div class="form-group"><label>ラベル</label><input value="${this.esc(q.label)}" onchange="PlansPage.questions[${i}].label=this.value" placeholder="ユーザーに表示する質問文"></div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>タイプ</label>
                        <select onchange="PlansPage.onQuestionTypeChange(${i},this.value)">
                            ${Object.entries(T).map(([v, l]) =>
                                `<option value="${v}" ${q.question_type===v?'selected':''}>${l}</option>`
                            ).join('')}
                        </select>
                    </div>
                    <div class="form-group"><label><input type="checkbox" ${q.is_required?'checked':''} onchange="PlansPage.questions[${i}].is_required=this.checked">必須</label></div>
                    <div class="form-group"><label><input type="checkbox" ${q.track_changes?'checked':''} onchange="PlansPage.questions[${i}].track_changes=this.checked">変更履歴を記録</label></div>
                </div>
                ${optionsHtml}
                ${arrayHtml}
            </div>`;
        }).join('');
    },

    getSelectedWeekdays() {
        return Array.from(document.querySelectorAll('.weekday-cb:checked')).map(cb => parseInt(cb.value));
    },

    async save() {
        const errEl = document.getElementById('plan-modal-error');
        errEl.textContent = '';

        const scheduleType = document.getElementById('p-schedule-type').value;
        const data = {
            name: document.getElementById('p-name').value,
            description: document.getElementById('p-desc').value,
            price: parseInt(document.getElementById('p-price').value) || 0,
            schedule_type: scheduleType,
            schedule_weekdays: scheduleType === 'weekday' ? this.getSelectedWeekdays() : null,
            send_time: document.getElementById('p-send-time').value,
            sheets_id: document.getElementById('p-sheets-id').value || null,
            model: document.getElementById('p-model').value,
            system_prompt: document.getElementById('p-system-prompt').value || null,
            prompt: document.getElementById('p-prompt').value,
            batch_send_enabled: document.getElementById('p-batch').checked,
            trial_enabled: document.getElementById('p-trial').checked,
        };

        if (!data.name || !data.prompt || !data.send_time) {
            errEl.textContent = 'プラン名、個別指示、配信時刻は必須です';
            return;
        }

        try {
            let planId = this.editingId;
            if (planId) {
                data.is_active = document.getElementById('p-active').checked;
                await API.put(`/api/admin/plans/${planId}`, data);
            } else {
                const res = await API.post('/api/admin/plans', data);
                planId = res.id;
            }

            // 質問項目保存
            if (this.questions.length > 0) {
                await API.put(`/api/admin/plans/${planId}/questions`, this.questions);
            }

            // あらすじ設定
            if (document.getElementById('s-enabled').checked) {
                const sPrompt = document.getElementById('s-prompt').value;
                if (sPrompt) {
                    await API.put(`/api/admin/plans/${planId}/summary-setting`, {
                        summary_prompt: sPrompt,
                        summary_length_target: parseInt(document.getElementById('s-length').value) || 200,
                        summary_max_keep: parseInt(document.getElementById('s-max-keep').value) || 10,
                        summary_inject_count: parseInt(document.getElementById('s-inject').value) || 3,
                    });
                }
            } else if (this.editingId) {
                // OFF → 既存設定を削除
                try { await API.del(`/api/admin/plans/${planId}/summary-setting`); } catch {}
            }

            // 外部データ設定
            const ePath = document.getElementById('e-path').value;
            if (ePath) {
                await API.put(`/api/admin/plans/${planId}/external-data-setting`, {
                    external_data_path: ePath,
                    firebase_key_json: this.firebaseKeyJson || null,
                });
            }

            this.closeModal();
            await this.loadPlans();
        } catch (e) {
            errEl.textContent = e.message;
        }
    },

    async testExternalData() {
        const resultEl = document.getElementById('external-test-result');
        const path = document.getElementById('e-path').value;
        if (!path) {
            resultEl.innerHTML = '<span style="color:#dc3545;">Firestoreパスを入力してください</span>';
            return;
        }
        resultEl.innerHTML = '<span style="color:#888;">テスト中...</span>';

        const body = { external_data_path: path };
        if (this.firebaseKeyJson) {
            body.firebase_key_json = this.firebaseKeyJson;
        } else if (this.editingId) {
            body.plan_id = this.editingId;
        }

        try {
            const res = await API.post('/api/admin/plans/test-external-data', body);
            if (!res.ok) {
                resultEl.innerHTML = `<div style="background:#fef2f2;border:1px solid #e0c0c0;border-radius:8px;padding:12px;font-size:13px;">
                    <strong style="color:#dc3545;">接続失敗</strong><br>
                    <span style="color:#666;">${this.esc(res.error)}</span>
                </div>`;
                return;
            }
            if (res.split) {
                const keyList = res.keys.map(k => `<li>${this.esc(k)}</li>`).join('');
                resultEl.innerHTML = `<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px;font-size:13px;">
                    <strong style="color:#16a34a;">接続OK</strong> — 分割処理対象: <strong>${res.keys.length}件</strong>
                    <ul style="margin:8px 0 0 16px;color:#333;">${keyList}</ul>
                </div>`;
            } else {
                const preview = res.preview || '(データなし)';
                resultEl.innerHTML = `<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px;font-size:13px;">
                    <strong style="color:#16a34a;">接続OK</strong>
                    <pre style="margin:8px 0 0;background:#f8f8f8;padding:8px;border-radius:4px;font-size:12px;max-height:200px;overflow:auto;white-space:pre-wrap;">${this.esc(preview)}</pre>
                </div>`;
            }
        } catch (e) {
            resultEl.innerHTML = `<span style="color:#dc3545;">エラー: ${this.esc(e.message)}</span>`;
        }
    },

    async testSheets() {
        const resultEl = document.getElementById('sheets-test-result');
        const sheetsId = document.getElementById('p-sheets-id').value;
        if (!sheetsId) {
            resultEl.innerHTML = '<span style="color:#dc3545;">Sheets IDを入力してください</span>';
            return;
        }
        resultEl.innerHTML = '<span style="color:#888;">テスト中...</span>';

        try {
            const res = await API.post('/api/admin/plans/test-sheets', { sheets_id: sheetsId });
            if (!res.ok) {
                resultEl.innerHTML = `<div style="background:#fef2f2;border:1px solid #e0c0c0;border-radius:8px;padding:12px;font-size:13px;">
                    <strong style="color:#dc3545;">接続失敗</strong><br>
                    <span style="color:#666;">${this.esc(res.error)}</span>
                </div>`;
                return;
            }
            const todayBadge = res.is_today
                ? '<span style="background:#16a34a;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">本日は配信対象</span>'
                : '<span style="background:#e0e0e0;color:#666;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">本日は配信対象外</span>';
            const datesList = res.dates.length > 0
                ? `<div style="margin-top:8px;"><strong>配信日程 (${res.dates.length}件):</strong><div style="margin-top:4px;max-height:150px;overflow:auto;font-size:12px;color:#333;">${res.dates.map(d => {
                    const isToday = d === res.today;
                    return isToday
                        ? `<span style="display:inline-block;margin:2px 4px;padding:2px 8px;background:#111;color:#fff;border-radius:4px;">${d}</span>`
                        : `<span style="display:inline-block;margin:2px 4px;padding:2px 8px;background:#f5f5f5;border-radius:4px;">${d}</span>`;
                }).join('')}</div></div>`
                : '<div style="margin-top:4px;color:#888;font-size:12px;">日付データなし</div>';
            resultEl.innerHTML = `<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px;font-size:13px;">
                <strong style="color:#16a34a;">接続OK</strong> — シート: ${this.esc(res.sheet_name)} ${todayBadge}
                ${datesList}
            </div>`;
        } catch (e) {
            resultEl.innerHTML = `<span style="color:#dc3545;">エラー: ${this.esc(e.message)}</span>`;
        }
    },

    async deletePlan(id, name) {
        if (!confirm(`プラン「${name}」を削除しますか？\n加入者がいる場合、全購読が強制解約されます。`)) return;
        try {
            await API.del(`/api/admin/plans/${id}`);
            await this.loadPlans();
        } catch (e) {
            alert(e.message);
        }
    },

    esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    },
};

// あらすじトグル監視
document.addEventListener('change', (e) => {
    if (e.target.id === 's-enabled') PlansPage.onSummaryToggle();
});
