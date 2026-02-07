"""認証ルーター: 登録、メール認証、ログイン、ログアウト、パスワードリセット"""
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.session import create_session, destroy_session, refresh_session_id, get_session
from app.core.csrf import generate_csrf_token
from app.core.config import settings
from app.core.rate_limit import (
    limiter,
    LOGIN_RATE_LIMIT,
    REGISTER_RATE_LIMIT,
    PASSWORD_RESET_RATE_LIMIT,
    VERIFY_CODE_RATE_LIMIT,
)
from app.schemas.auth import (
    RegisterRequest,
    VerifyEmailRequest,
    LoginRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    AuthResponse,
    UserInfo,
)
from app.services import auth_service
from app.services.mail_service import send_verify_code_email, send_password_reset_email
from app.routers.deps import get_current_user, require_login

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
@limiter.limit(REGISTER_RATE_LIMIT)
async def register(request: Request, req: RegisterRequest, db: Session = Depends(get_db), r=Depends(get_redis)):
    """会員登録"""
    # 既存ユーザーチェック
    existing = auth_service.get_user_by_email(db, req.email)
    if existing:
        raise HTTPException(status_code=400, detail="このメールアドレスは既に登録されています")

    # ユーザー作成
    user = auth_service.create_user(
        db=db,
        email=req.email,
        password=req.password,
        name_last=req.name_last,
        name_first=req.name_first,
    )

    # 認証コード生成・送信
    code = await auth_service.generate_verify_code(r, user.id)
    if code:
        send_verify_code_email(
            to_email=user.email,
            name=f"{user.name_last} {user.name_first}",
            code=code,
        )

    return AuthResponse(message="登録完了。メール認証コードを送信しました。", user_id=user.id)


@router.post("/verify-email", response_model=AuthResponse)
@limiter.limit(VERIFY_CODE_RATE_LIMIT)
async def verify_email(
    request: Request,
    req: VerifyEmailRequest,
    response: Response,
    db: Session = Depends(get_db),
    r=Depends(get_redis),
):
    """メール認証コード検証"""
    success, msg = await auth_service.verify_code(r, req.user_id, req.code)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    # メール認証済みに更新
    user = auth_service.get_user_by_id(db, req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    user.email_verified = True
    db.commit()

    # セッション作成
    session_id = await create_session(r, user.id, user.role, user.member_no, user.email)
    csrf_token = await generate_csrf_token(session_id)

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=not settings.DEBUG,  # 本番(DEBUG=False)ではTrue
        samesite="lax",
        max_age=settings.SESSION_TIMEOUT_MINUTES * 60,
    )
    response.headers["X-CSRF-Token"] = csrf_token

    return AuthResponse(message="メール認証完了", csrf_token=csrf_token)


@router.post("/resend-code", response_model=AuthResponse)
@limiter.limit(VERIFY_CODE_RATE_LIMIT)
async def resend_verify_code(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    r=Depends(get_redis),
):
    """認証コード再送"""
    user = auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    code = await auth_service.generate_verify_code(r, user.id)
    if code is None:
        raise HTTPException(status_code=429, detail="認証がロックされています。しばらくお待ちください。")

    send_verify_code_email(
        to_email=user.email,
        name=f"{user.name_last} {user.name_first}",
        code=code,
    )
    return AuthResponse(message="認証コードを再送しました")


@router.post("/login", response_model=AuthResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(
    request: Request,
    req: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    r=Depends(get_redis),
):
    """ログイン"""
    user = auth_service.get_user_by_email(db, req.email)
    if not user or not auth_service.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが正しくありません")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="このアカウントは無効化されています")

    if not user.email_verified:
        # 認証コード再送
        code = await auth_service.generate_verify_code(r, user.id)
        if code:
            send_verify_code_email(
                to_email=user.email,
                name=f"{user.name_last} {user.name_first}",
                code=code,
            )
        # セキュリティ: エラーメッセージにuser_idを含めず、専用フィールドで返す
        return JSONResponse(
            status_code=403,
            content={
                "detail": "メール認証が完了していません。認証コードを再送しました。",
                "needs_verification": True,
                "user_id": user.id,
            },
        )

    # セッション作成 (固定化攻撃対策: 毎回新規)
    session_id = await create_session(r, user.id, user.role, user.member_no, user.email)
    csrf_token = await generate_csrf_token(session_id)

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=not settings.DEBUG,  # 本番(DEBUG=False)ではTrue
        samesite="lax",
        max_age=settings.SESSION_TIMEOUT_MINUTES * 60,
    )
    response.headers["X-CSRF-Token"] = csrf_token

    return AuthResponse(message="ログイン成功", csrf_token=csrf_token)


@router.post("/logout")
async def logout(request: Request, response: Response, r=Depends(get_redis)):
    """ログアウト"""
    session_id = request.cookies.get("session_id")
    if session_id:
        await destroy_session(r, session_id)
    response.delete_cookie("session_id")
    return {"message": "ログアウトしました"}


@router.post("/password-reset/request", response_model=AuthResponse)
@limiter.limit(PASSWORD_RESET_RATE_LIMIT)
async def request_password_reset(
    request: Request,
    req: PasswordResetRequest,
    db: Session = Depends(get_db),
    r=Depends(get_redis),
):
    """パスワードリセット要求"""
    user = auth_service.get_user_by_email(db, req.email)
    # ユーザーの存在有無に関わらず同じレスポンス (情報漏洩防止)
    if user and user.is_active:
        token = await auth_service.create_reset_token(r, user.id)
        reset_url = f"{settings.SITE_URL}/password-reset.html?token={token}"
        send_password_reset_email(
            to_email=user.email,
            name=f"{user.name_last} {user.name_first}",
            reset_url=reset_url,
        )
    return AuthResponse(message="リセットメールを送信しました（登録済みの場合）")


@router.post("/password-reset/confirm", response_model=AuthResponse)
@limiter.limit(PASSWORD_RESET_RATE_LIMIT)
async def confirm_password_reset(
    request: Request,
    req: PasswordResetConfirm,
    db: Session = Depends(get_db),
    r=Depends(get_redis),
):
    """パスワードリセット実行"""
    user_id = await auth_service.validate_reset_token(r, req.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="リセットトークンが無効または期限切れです")

    user = auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    user.password_hash = auth_service.hash_password(req.new_password)
    db.commit()

    return AuthResponse(message="パスワードをリセットしました")


@router.get("/me", response_model=UserInfo)
async def get_me(user=Depends(require_login)):
    """現在のログインユーザー情報"""
    return UserInfo.model_validate(user)
