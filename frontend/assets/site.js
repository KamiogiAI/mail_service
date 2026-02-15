/**
 * サイト名動的読み込み + ヘッダーナビ認証切替 + モバイルメニュー
 * 全ページで /assets/site.js として読み込む
 */
(function() {
    // サイト名を動的に反映
    fetch('/api/pages')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.site_name) return;
            document.querySelectorAll('.site-name').forEach(function(el) {
                el.textContent = data.site_name;
            });
            var t = document.title;
            if (t) {
                document.title = data.site_name + ' - ' + t;
            }
        })
        .catch(function() {});

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    // モバイルメニュー要素を挿入
    function setupMobileMenu() {
        var header = document.querySelector('.header');
        if (!header) return;

        // ハンバーガーボタン
        var hamburger = document.createElement('button');
        hamburger.className = 'hamburger';
        hamburger.setAttribute('aria-label', 'メニュー');
        hamburger.innerHTML = '<span></span><span></span><span></span>';
        header.appendChild(hamburger);

        // オーバーレイ
        var overlay = document.createElement('div');
        overlay.className = 'nav-overlay';
        document.body.appendChild(overlay);

        // モバイルナビ
        var mobileNav = document.createElement('div');
        mobileNav.className = 'mobile-nav';
        mobileNav.id = 'mobile-nav';
        document.body.appendChild(mobileNav);

        // トグル
        function toggle() {
            hamburger.classList.toggle('active');
            overlay.classList.toggle('active');
            mobileNav.classList.toggle('active');
            document.body.style.overflow = mobileNav.classList.contains('active') ? 'hidden' : '';
        }

        hamburger.addEventListener('click', toggle);
        overlay.addEventListener('click', toggle);

        // ナビリンクでも閉じる
        mobileNav.addEventListener('click', function(e) {
            if (e.target.tagName === 'A') {
                toggle();
            }
        });
    }

    // モバイルナビの内容を更新
    function updateMobileNav(html) {
        var mobileNav = document.getElementById('mobile-nav');
        if (mobileNav) {
            mobileNav.innerHTML = html;
        }
    }

    // DOMContentLoaded で実行
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupMobileMenu);
    } else {
        setupMobileMenu();
    }

    // 認証チェック → ヘッダーナビ切替
    fetch('/api/auth/me', { credentials: 'include' })
        .then(function(r) {
            if (!r.ok) throw new Error();
            return r.json();
        })
        .then(function(user) {
            // ログイン中: ○○様 | マイページ | ログアウト
            var nav = document.getElementById('header-nav');
            var fullName = ((user.name_last || '') + ' ' + (user.name_first || '')).trim();
            var navHtml =
                '<span class="nav-user-name">' + esc(fullName || 'ユーザー') + ' 様</span>' +
                '<a href="/form/user/mypage.html">マイページ</a>' +
                '<a href="#" onclick="siteLogout();return false;">ログアウト</a>';
            if (nav) nav.innerHTML = navHtml;
            updateMobileNav(navHtml);
        })
        .catch(function() {
            // ログアウト中: ログイン | 新規登録
            var nav = document.getElementById('header-nav');
            var navHtml =
                '<a href="/form/login.html">ログイン</a>' +
                '<a href="/form/register.html">新規登録</a>';
            if (nav) nav.innerHTML = navHtml;
            updateMobileNav(navHtml);
        });
})();

/** ログアウト (全ページ共通) */
function siteLogout() {
    var csrf = localStorage.getItem('csrf_token');
    var headers = { 'Content-Type': 'application/json' };
    if (csrf) headers['X-CSRF-Token'] = csrf;
    fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: headers,
    })
    .then(function() {})
    .catch(function() {})
    .finally(function() {
        localStorage.removeItem('csrf_token');
        location.href = '/form/login.html';
    });
}
