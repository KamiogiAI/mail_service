/**
 * サービス設定画面
 */
const SettingsPage = {
    async render(container) {
        container.innerHTML = `
            <div class="content-header"><h1>サービス設定</h1></div>
            <div id="settings-form" class="loading">読み込み中...</div>
        `;
        await this.load();
    },

    async load() {
        try {
            const s = await API.get('/api/admin/settings');
            document.getElementById('settings-form').classList.remove('loading');
            document.getElementById('settings-form').innerHTML = `
                <div class="card">
                    <div class="card-header"><h2>基本設定</h2></div>
                    <div class="form-group"><label>サイト名</label><input id="set-site-name" value="${s.site_name || ''}"></div>
                    <div class="form-group"><label>サイトURL</label><input id="set-site-url" value="${s.site_url || ''}"></div>
                    <div class="form-group"><label>送信元メール</label><input id="set-from-email" value="${s.from_email || ''}"></div>
                </div>
                <div class="card">
                    <div class="card-header"><h2>APIキー</h2></div>
                    <div class="form-group"><label>OpenAI API Key</label><input id="set-openai" placeholder="${s.openai_api_key_masked || '未設定'}"></div>
                    <div class="form-group"><label>Resend API Key</label><input id="set-resend" placeholder="${s.resend_api_key_masked || '未設定'}"></div>
                    <div class="form-group"><label>Stripe Secret Key</label><input id="set-stripe-secret" placeholder="${s.stripe_secret_key_masked || '未設定'}"></div>
                    <div class="form-group"><label>Stripe Publishable Key</label><input id="set-stripe-pub" value="${s.stripe_publishable_key || ''}"></div>
                    <div class="form-group"><label>Stripe Webhook Secret</label><input id="set-stripe-wh" placeholder="${s.stripe_webhook_secret_masked || '未設定'}"></div>
                    <div class="form-group"><label>Resend Webhook Secret</label><input id="set-resend-wh" placeholder="${s.resend_webhook_secret_masked || '未設定'}"></div>
                    <small>空欄の場合は変更されません。新しい値を入力すると上書きします。</small>
                </div>
                <div class="card">
                    <div class="card-header"><h2>Firebase設定 (Google Sheets連携)</h2></div>
                    <div class="form-group">
                        <label>Firebase Key JSON</label>
                        <input type="file" id="set-firebase-file" accept=".json" onchange="SettingsPage.onFirebaseFileSelected()">
                        <span id="set-firebase-preview" style="margin-left:8px;color:#666;"></span>
                    </div>
                    ${s.firebase_client_email ? `<div class="form-group" style="background:#f0f9ff;padding:10px;border-radius:4px;">
                        <strong>設定済み:</strong> スプレッドシートを <code>${s.firebase_client_email}</code> に共有してください
                    </div>` : '<div class="form-group" style="color:#999;">Firebase Key JSONが未設定です</div>'}
                </div>
                <div class="card">
                    <div class="card-header"><h2>機能設定</h2></div>
                    <div class="form-group"><label><input type="checkbox" id="set-resend-webhook" ${s.resend_webhook_enabled ? 'checked' : ''}>Resend Webhook有効</label></div>
                    <div class="form-group"><label><input type="checkbox" id="set-multi-plan" ${s.allow_multiple_plans ? 'checked' : ''}>複数プラン同時加入許可</label></div>
                </div>
                <div class="card">
                    <div class="card-header"><h2>静的ページ (Markdown)</h2></div>
                    <div class="tabs">
                        <button class="tab-btn active" onclick="SettingsPage.switchPageTab(event,'terms')">利用規約</button>
                        <button class="tab-btn" onclick="SettingsPage.switchPageTab(event,'company')">運営会社</button>
                        <button class="tab-btn" onclick="SettingsPage.switchPageTab(event,'cancel')">キャンセルポリシー</button>
                        <button class="tab-btn" onclick="SettingsPage.switchPageTab(event,'tokusho')">特商法表記</button>
                        <button class="tab-btn" onclick="SettingsPage.switchPageTab(event,'privacy')">プライバシーポリシー</button>
                    </div>
                    <div id="page-terms" class="tab-content active"><textarea id="set-terms" rows="10" style="width:100%;min-width:600px;">${s.terms_md || ''}</textarea></div>
                    <div id="page-company" class="tab-content"><textarea id="set-company" rows="10" style="width:100%;min-width:600px;">${s.company_md || ''}</textarea></div>
                    <div id="page-cancel" class="tab-content"><textarea id="set-cancel" rows="10" style="width:100%;min-width:600px;">${s.cancel_md || ''}</textarea></div>
                    <div id="page-tokusho" class="tab-content"><textarea id="set-tokusho" rows="10" style="width:100%;min-width:600px;">${s.tokusho_md || ''}</textarea></div>
                    <div id="page-privacy" class="tab-content"><textarea id="set-privacy" rows="10" style="width:100%;min-width:600px;">${s.privacy_md || ''}</textarea></div>
                </div>
                <button class="btn" onclick="SettingsPage.save()">保存</button>
                <span id="settings-msg" class="success-message" style="margin-left:10px;"></span>
            `;
        } catch (e) {
            document.getElementById('settings-form').innerHTML = `<p class="error-message">${e.message}</p>`;
        }
    },

    firebaseKeyJson: null,

    onFirebaseFileSelected() {
        const file = document.getElementById('set-firebase-file').files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (e) => {
            SettingsPage.firebaseKeyJson = e.target.result;
            try {
                const parsed = JSON.parse(e.target.result);
                document.getElementById('set-firebase-preview').textContent =
                    parsed.client_email ? `client_email: ${parsed.client_email}` : file.name + ' 読み込み済み';
            } catch {
                document.getElementById('set-firebase-preview').textContent = file.name + ' 読み込み済み';
            }
        };
        reader.readAsText(file);
    },

    switchPageTab(e, name) {
        document.querySelectorAll('#settings-form .tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('#settings-form .tab-content').forEach(c => c.classList.remove('active'));
        e.target.classList.add('active');
        document.getElementById('page-' + name).classList.add('active');
    },

    async save() {
        const data = {
            site_name: document.getElementById('set-site-name').value,
            site_url: document.getElementById('set-site-url').value,
            from_email: document.getElementById('set-from-email').value,
            stripe_publishable_key: document.getElementById('set-stripe-pub').value,
            resend_webhook_enabled: document.getElementById('set-resend-webhook').checked,
            allow_multiple_plans: document.getElementById('set-multi-plan').checked,
            terms_md: document.getElementById('set-terms').value,
            company_md: document.getElementById('set-company').value,
            cancel_md: document.getElementById('set-cancel').value,
            tokusho_md: document.getElementById('set-tokusho').value,
            privacy_md: document.getElementById('set-privacy').value,
        };

        // APIキーは入力がある場合のみ送信
        const openai = document.getElementById('set-openai').value;
        if (openai) data.openai_api_key = openai;
        const resend = document.getElementById('set-resend').value;
        if (resend) data.resend_api_key = resend;
        const stripeSecret = document.getElementById('set-stripe-secret').value;
        if (stripeSecret) data.stripe_secret_key = stripeSecret;
        const stripeWh = document.getElementById('set-stripe-wh').value;
        if (stripeWh) data.stripe_webhook_secret = stripeWh;
        const resendWh = document.getElementById('set-resend-wh').value;
        if (resendWh) data.resend_webhook_secret = resendWh;

        if (this.firebaseKeyJson) data.firebase_key_json = this.firebaseKeyJson;

        try {
            await API.put('/api/admin/settings', data);
            document.getElementById('settings-msg').textContent = '保存しました';
            setTimeout(() => document.getElementById('settings-msg').textContent = '', 3000);
        } catch (e) {
            alert(e.message);
        }
    },
};
