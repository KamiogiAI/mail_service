import secrets
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.redis import get_redis
from app.core.logging import get_logger

logger = get_logger(__name__)

CSRF_PREFIX = "csrf:"
CSRF_TTL = 3600 * 2  # 2時間

# CSRF検証を免除するパス（前方一致でチェック）
# trailing slashの有無に関わらずマッチさせるため
CSRF_EXEMPT_PATHS = [
    "/api/webhooks/stripe",
    "/api/webhooks/resend",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/verify-email",
    "/api/auth/resend-code",
    "/api/auth/password-reset/request",
    "/api/auth/password-reset/confirm",
    "/api/checkout-complete",
]

# CSRF検証対象メソッド
CSRF_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def _is_csrf_exempt(path: str) -> bool:
    """パスがCSRF免除対象かチェック（前方一致 or 完全一致）"""
    # trailing slashを除去して比較
    normalized = path.rstrip("/")
    for exempt_path in CSRF_EXEMPT_PATHS:
        if normalized == exempt_path or normalized.startswith(exempt_path + "/"):
            return True
    return False


async def generate_csrf_token(session_id: str) -> str:
    """CSRFトークンを生成してRedisに保存"""
    token = secrets.token_hex(32)
    r = await get_redis()
    await r.set(f"{CSRF_PREFIX}{session_id}", token, ex=CSRF_TTL)
    return token


async def validate_csrf_token(session_id: str, token: str) -> bool:
    """CSRFトークンを検証"""
    if not session_id or not token:
        return False
    r = await get_redis()
    stored = await r.get(f"{CSRF_PREFIX}{session_id}")
    return stored is not None and stored == token


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF保護ミドルウェア"""

    async def dispatch(self, request: Request, call_next):
        if request.method not in CSRF_METHODS:
            return await call_next(request)

        # 免除パスチェック（前方一致）
        if _is_csrf_exempt(request.url.path):
            return await call_next(request)

        # セッションIDをCookieから取得
        session_id = request.cookies.get("session_id")
        if not session_id:
            logger.warning(f"CSRF検証失敗（セッションなし）: path={request.url.path}")
            raise HTTPException(status_code=403, detail="CSRFトークンが無効です")

        # ヘッダーからCSRFトークン取得
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not await validate_csrf_token(session_id, csrf_token):
            logger.warning(f"CSRF検証失敗（トークン不一致）: path={request.url.path}")
            raise HTTPException(status_code=403, detail="CSRFトークンが無効です")

        return await call_next(request)
