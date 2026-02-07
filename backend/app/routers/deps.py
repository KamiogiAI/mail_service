"""共通依存関数: 認証・ロール制御"""
from typing import Optional
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.session import get_session
from app.models.user import User


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    r=Depends(get_redis),
) -> Optional[User]:
    """Cookie → Redis → DB でユーザー取得。未ログインならNone"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None

    session_data = await get_session(r, session_id)
    if not session_data:
        return None

    user_id = int(session_data.get("user_id", 0))
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user


async def require_login(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """ログイン必須。未ログインなら401"""
    if user is None:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return user


async def require_admin(
    user: User = Depends(require_login),
) -> User:
    """管理者権限必須。adminでなければ403"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="管理者権限が必要です")
    return user
