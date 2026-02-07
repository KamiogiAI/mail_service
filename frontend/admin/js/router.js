/**
 * ハッシュベースルーティング
 */
const Router = {
    routes: {},
    currentPage: null,

    /** ルート登録 */
    register(hash, handler) {
        this.routes[hash] = handler;
    },

    /** ルーティング開始 */
    start() {
        window.addEventListener('hashchange', () => this.navigate());
        this.navigate();
    },

    /** 現在のハッシュに基づいてページ表示 */
    navigate() {
        const hash = location.hash.replace('#', '') || 'dashboard';
        const handler = this.routes[hash];

        // サイドバーのアクティブ状態更新
        document.querySelectorAll('.sidebar-menu li').forEach(li => {
            li.classList.toggle('active', li.dataset.page === hash);
        });

        // コンテンツエリアをクリア
        const content = document.getElementById('page-content');
        if (!content) return;

        if (handler) {
            this.currentPage = hash;
            handler(content);
        } else {
            content.innerHTML = '<p>ページが見つかりません</p>';
        }
    },
};
