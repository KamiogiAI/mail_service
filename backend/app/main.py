from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
import asyncio
import redis.exceptions as redis_exceptions
from app.core.csrf import CSRFMiddleware, touch_csrf_token
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import health, auth, subscriptions, webhooks_stripe, webhooks_resend
from app.routers import plans, pages, me
from app.routers import admin_plans, admin_users, admin_promotions, settings as settings_router
from app.routers import admin_progress, admin_logs, admin_manual_send, admin_deliveries, admin_subscriptions, admin_dashboard
from app.routers import admin_firebase

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフサイクル管理"""
    setup_logging(debug=settings.DEBUG)
    
    # 必須設定値のチェック
    if not settings.JWT_SECRET or settings.JWT_SECRET == "dev-secret-change-me":
        raise RuntimeError("JWT_SECRET が設定されていません。.envファイルで強いランダム値を設定してください。")
    if len(settings.JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET は32文字以上の強い値を設定してください。")
    
    logger.info("アプリケーション起動")
    yield
    logger.info("アプリケーション終了")


app = FastAPI(
    title=settings.SITE_NAME,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
)

# レート制限設定
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# --- バリデーションエラー日本語化 ---
_FIELD_JA = {
    "email": "メールアドレス",
    "password": "パスワード",
    "new_password": "新しいパスワード",
    "current_password": "現在のパスワード",
    "name_last": "姓",
    "name_first": "名",
    "code": "認証コード",
    "token": "トークン",
    "plan_id": "プランID",
    "user_id": "ユーザーID",
    "role": "ロール",
    "price": "価格",
    "name": "名前",
    "prompt": "プロンプト",
    "send_time": "送信時刻",
    "plan_ids": "プランID一覧",
    "discount_type": "割引タイプ",
    "discount_value": "割引値",
    "subject": "件名",
    "body": "本文",
    "promotion_code": "プロモーションコード",
    "session_id": "セッションID",
}


def _translate_error(err: dict) -> str:
    t = err.get("type", "")
    ctx = err.get("ctx", {})
    loc = err.get("loc", [])
    field = str(loc[-1]) if loc else ""
    fj = _FIELD_JA.get(field, field)

    if "email" in t or ("value" in t and "email" in err.get("msg", "").lower()):
        return f"{fj}は有効なメールアドレス形式で入力してください"
    if t == "string_too_short":
        return f"{fj}は{ctx.get('min_length', '')}文字以上で入力してください"
    if t == "string_too_long":
        return f"{fj}は{ctx.get('max_length', '')}文字以下で入力してください"
    if t == "missing":
        return f"{fj}は必須です"
    if t in ("int_parsing", "int_type"):
        return f"{fj}は数値で入力してください"
    if t == "greater_than_equal":
        return f"{fj}は{ctx.get('ge', '')}以上の値を入力してください"
    if t == "less_than_equal":
        return f"{fj}は{ctx.get('le', '')}以下の値を入力してください"
    if t == "string_type":
        return f"{fj}は文字列で入力してください"
    if t == "bool_parsing":
        return f"{fj}は真偽値で入力してください"
    return f"{fj}: 入力値が不正です"


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    messages = [_translate_error(e) for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "、".join(messages)})


# ミドルウェア (登録順序: 後に登録したものが先に実行される)
# セキュリティヘッダー（最初に実行されるよう最後に登録）
app.add_middleware(SecurityHeadersMiddleware)

# CSRF保護
app.add_middleware(CSRFMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-CSRF-Token"],
)


_CSRF_ROTATE_SKIP_PREFIXES = ("/api/webhooks/", "/static/")


@app.middleware("http")
async def csrf_token_rotate(request: Request, call_next):
    """session_id がある全レスポンスで CSRF token を touch し header に載せる。

    2h TTL で CSRF token が Redis から消えても、次回レスポンス (GET含む) で新規発行して
    フロントの localStorage に伝播させ、POST/PUT/DELETE が 403 で詰まるのを防ぐ。
    CSRFMiddleware は 403 を raise ではなく JSONResponse で返すようにしたので、
    403 でもここで header を付けられる (POST 直後にフロントが再取得できる)。

    スキップ条件: OPTIONS preflight、webhook/静的ファイル、session 不在。
    Redis 障害時はログのみ出して response は返す (graceful degradation)。
    """
    response = await call_next(request)

    # OPTIONS preflight と webhook/静的は rotate 不要
    if request.method == "OPTIONS":
        return response
    path = request.url.path
    if any(path.startswith(p) for p in _CSRF_ROTATE_SKIP_PREFIXES):
        return response

    session_id = request.cookies.get("session_id")
    if not session_id:
        return response

    # login/verify-email は response.headers["X-CSRF-Token"] を handler 側で既に set 済。
    # touch は値を変えない想定だが、上書き回避で安全側に倒す。
    if "X-CSRF-Token" in response.headers:
        # CDN 汚染防止で Vary だけは確実に付ける
        _append_vary_cookie(response)
        return response

    try:
        token = await touch_csrf_token(session_id)
    except (redis_exceptions.RedisError, asyncio.TimeoutError, ConnectionError) as e:
        logger.warning(f"CSRF token rotation failed: {e}")
        return response

    if token:
        response.headers["X-CSRF-Token"] = token
        _append_vary_cookie(response)
    return response


def _append_vary_cookie(response) -> None:
    """既存 Vary と重複しない形で Cookie を追記 (CDN キャッシュ汚染防止)"""
    existing = response.headers.get("Vary", "")
    tokens = {t.strip() for t in existing.split(",") if t.strip()}
    tokens.add("Cookie")
    response.headers["Vary"] = ", ".join(sorted(tokens))


# ルーター登録
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(subscriptions.router)
app.include_router(webhooks_stripe.router)
app.include_router(webhooks_resend.router)
app.include_router(admin_plans.router)
app.include_router(admin_users.router)
app.include_router(admin_promotions.router)
app.include_router(settings_router.router)
app.include_router(admin_progress.router)
app.include_router(admin_logs.router)
app.include_router(admin_manual_send.router)
app.include_router(admin_deliveries.router)
app.include_router(admin_subscriptions.router)
app.include_router(admin_dashboard.router)
app.include_router(admin_firebase.router)
app.include_router(plans.router)
app.include_router(pages.router)
app.include_router(me.router)
