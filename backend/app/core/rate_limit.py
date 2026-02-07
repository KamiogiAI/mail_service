"""レート制限設定（slowapi使用）"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse


def get_client_ip(request: Request) -> str:
    """
    クライアントIPアドレスを取得
    プロキシ経由の場合はX-Forwarded-Forヘッダーを参照
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # カンマ区切りの最初のIPを取得
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Limiterインスタンス（アプリケーション全体で共有）
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=["100/minute"],  # デフォルト: 100回/分
    storage_uri="memory://",  # 本番ではRedisを推奨: "redis://localhost:6379"
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    レート制限超過時のカスタムエラーハンドラ
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "リクエスト回数が上限を超えました。しばらく待ってから再度お試しください。",
            "retry_after": exc.detail,
        },
    )


# エンドポイント別のレート制限定義
# 使用例:
#   @router.post("/login")
#   @limiter.limit(LOGIN_RATE_LIMIT)
#   async def login(request: Request, ...):

LOGIN_RATE_LIMIT = "5/minute"       # ログイン: 5回/分
REGISTER_RATE_LIMIT = "3/minute"    # 登録: 3回/分
GENERAL_RATE_LIMIT = "100/minute"   # 一般API: 100回/分
PASSWORD_RESET_RATE_LIMIT = "3/minute"  # パスワードリセット: 3回/分
VERIFY_CODE_RATE_LIMIT = "5/minute"     # 認証コード関連: 5回/分
