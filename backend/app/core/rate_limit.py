"""レート制限設定（slowapi使用）"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse


# 信頼するプロキシのIPアドレス（Nginxなど）
# 本番では実際のプロキシIPをここに列挙する
TRUSTED_PROXIES = {
    "127.0.0.1",
    "::1",
    "172.16.0.0/12",  # Docker内部ネットワーク
}


def _is_trusted_proxy(ip: str) -> bool:
    """プロキシIPが信頼できるものかチェック"""
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        for trusted in TRUSTED_PROXIES:
            try:
                if "/" in trusted:
                    if addr in ipaddress.ip_network(trusted, strict=False):
                        return True
                else:
                    if addr == ipaddress.ip_address(trusted):
                        return True
            except ValueError:
                continue
    except ValueError:
        pass
    return False


def get_client_ip(request: Request) -> str:
    """
    クライアントIPアドレスを取得
    信頼できるプロキシからのリクエストのみX-Forwarded-Forを参照する。
    直接接続または信頼できないプロキシの場合はTCPの接続元IPを使用。
    (X-Forwarded-Forをそのまま信頼するとレート制限バイパスが可能になる)
    """
    direct_ip = get_remote_address(request)
    if _is_trusted_proxy(direct_ip):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # カンマ区切りの最初のIPを取得 (クライアントIP)
            return forwarded.split(",")[0].strip()
    return direct_ip


# Limiterインスタンス（アプリケーション全体で共有）
# Redisを使用して分散環境でもレート制限を共有
from app.core.config import settings

limiter = Limiter(
    key_func=get_client_ip,
    default_limits=["100/minute"],  # デフォルト: 100回/分
    storage_uri=settings.REDIS_URL,  # Redisを使用
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
