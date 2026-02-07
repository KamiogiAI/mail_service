/**
 * API通信モジュール (Cookie + CSRFヘッダー)
 */
const API = {
    csrfToken: null,
    baseUrl: '',

    /** CSRFトークン設定 */
    setCsrfToken(token) {
        this.csrfToken = token;
        localStorage.setItem('csrf_token', token);
    },

    /** 保存済みCSRFトークン復元 */
    restoreCsrfToken() {
        this.csrfToken = localStorage.getItem('csrf_token');
    },

    /** エラーメッセージ抽出 */
    _extractError(data) {
        if (!data || !data.detail) return 'エラーが発生しました';
        if (typeof data.detail === 'string') return data.detail;
        if (Array.isArray(data.detail)) return data.detail.map(e => e.msg || String(e)).join(', ');
        return String(data.detail);
    },

    /** リクエスト共通処理 */
    async request(method, path, body = null) {
        const opts = {
            method,
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
        };

        if (this.csrfToken && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            opts.headers['X-CSRF-Token'] = this.csrfToken;
        }

        if (body !== null) {
            opts.body = JSON.stringify(body);
        }

        const res = await fetch(this.baseUrl + path, opts);

        // CSRFトークン更新
        const newCsrf = res.headers.get('X-CSRF-Token');
        if (newCsrf) {
            this.setCsrfToken(newCsrf);
        }

        if (res.status === 401) {
            // セッション切れ → ログイン画面へ
            localStorage.removeItem('csrf_token');
            this.csrfToken = null;
            throw new Error('セッションが切れました');
        }

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'エラーが発生しました' }));
            throw new Error(this._extractError(err));
        }

        return res.json();
    },

    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },
    put(path, body) { return this.request('PUT', path, body); },
    del(path) { return this.request('DELETE', path); },
};

// 初期化
API.restoreCsrfToken();
