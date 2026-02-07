/**
 * ユーザー向けAPI通信モジュール
 */
const API = {
    csrfToken: localStorage.getItem('csrf_token'),

    _extractError(data) {
        if (!data || !data.detail) return 'エラーが発生しました';
        if (typeof data.detail === 'string') return data.detail;
        if (Array.isArray(data.detail)) return data.detail.map(e => e.msg || String(e)).join(', ');
        return String(data.detail);
    },

    async request(method, path, body = null) {
        const opts = {
            method,
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
        };
        if (this.csrfToken && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            opts.headers['X-CSRF-Token'] = this.csrfToken;
        }
        if (body !== null) opts.body = JSON.stringify(body);

        const res = await fetch(path, opts);
        const newCsrf = res.headers.get('X-CSRF-Token');
        if (newCsrf) {
            this.csrfToken = newCsrf;
            localStorage.setItem('csrf_token', newCsrf);
        }

        if (res.status === 401) {
            // 無限リダイレクト防止
            if (!location.pathname.includes('login.html')) {
                location.href = '/login.html';
            }
            throw new Error('ログインが必要です');
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
