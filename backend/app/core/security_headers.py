"""セキュリティヘッダーミドルウェア"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    セキュリティ関連のHTTPヘッダーを付与するミドルウェア
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # クリックジャッキング対策: iframeへの埋め込みを禁止
        response.headers["X-Frame-Options"] = "DENY"

        # MIMEタイプスニッフィング対策
        response.headers["X-Content-Type-Options"] = "nosniff"

        # HTTPS強制（HSTS）: 1年間、サブドメイン含む
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        # コンテンツセキュリティポリシー
        # - default-src 'self': 同一オリジンのみ許可
        # - script-src 'self' 'unsafe-inline': インラインスクリプト許可（必要に応じて調整）
        # - style-src 'self' 'unsafe-inline': インラインスタイル許可
        # - img-src 'self' data: https:: 画像は同一オリジン、data URI、HTTPS許可
        # - font-src 'self': フォントは同一オリジンのみ
        # - connect-src 'self': API接続は同一オリジンのみ
        # - frame-ancestors 'none': iframe埋め込み禁止
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        # XSS対策（レガシーブラウザ向け、CSPがあれば不要だが念のため）
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer情報の制限
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 機能ポリシー（Permissions Policy）
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        return response
