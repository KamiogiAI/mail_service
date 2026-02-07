"""認証ビジネスロジック"""
import secrets
import random
import string
import bcrypt
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from typing import Optional
import redis.asyncio as aioredis

from app.models.user import User
from app.core.logging import get_logger

logger = get_logger(__name__)

# 会員番号の開始値
MEMBER_NO_START = 10000001

# 認証コード設定
VERIFY_CODE_TTL = 600  # 10分
VERIFY_MAX_ATTEMPTS = 5
VERIFY_LOCK_TTL = 1800  # 30分
VERIFY_CODE_PREFIX = "verify_code:"
VERIFY_LOCK_PREFIX = "verify_lock:"

# パスワードリセット設定
RESET_TOKEN_PREFIX = "reset_token:"
RESET_TOKEN_TTL = 3600  # 1時間

# パスワード変更2FA設定
PASSWORD_CHANGE_TOKEN_PREFIX = "pw_change_token:"
PASSWORD_CHANGE_TOKEN_TTL = 600  # 10分


def hash_password(password: str) -> str:
    """パスワードをbcryptでハッシュ化"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """パスワードを検証"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def generate_member_no(db: Session) -> str:
    """8桁会員番号を自動採番"""
    result = db.query(sa_func.max(User.member_no)).scalar()
    if result is None:
        return str(MEMBER_NO_START)
    next_no = int(result) + 1
    return str(next_no)


def generate_unsubscribe_token() -> str:
    """配信停止トークン生成"""
    return secrets.token_hex(32)


def create_user(
    db: Session,
    email: str,
    password: str,
    name_last: str,
    name_first: str,
    role: str = "user",
) -> User:
    """新規ユーザー作成"""
    member_no = generate_member_no(db)
    user = User(
        member_no=member_no,
        email=email,
        password_hash=hash_password(password),
        name_last=name_last,
        name_first=name_first,
        role=role,
        email_verified=False,
        is_active=True,
        unsubscribe_token=generate_unsubscribe_token(),
        deliverable=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"ユーザー作成: member_no={member_no}, email={email}")
    return user


async def generate_verify_code(r: aioredis.Redis, user_id: int) -> Optional[str]:
    """認証コードを生成してRedisに保存"""
    lock_key = f"{VERIFY_LOCK_PREFIX}{user_id}"
    if await r.exists(lock_key):
        return None  # ロック中

    code = "".join(random.choices(string.digits, k=6))
    key = f"{VERIFY_CODE_PREFIX}{user_id}"
    import json
    data = json.dumps({"code": code, "attempts": 0})
    await r.set(key, data, ex=VERIFY_CODE_TTL)
    return code


async def verify_code(r: aioredis.Redis, user_id: int, input_code: str) -> tuple[bool, str]:
    """認証コードを検証。(成功フラグ, メッセージ)を返す"""
    import json

    lock_key = f"{VERIFY_LOCK_PREFIX}{user_id}"
    if await r.exists(lock_key):
        return False, "認証がロックされています。しばらくお待ちください。"

    key = f"{VERIFY_CODE_PREFIX}{user_id}"
    raw = await r.get(key)
    if not raw:
        return False, "認証コードが期限切れです。再送信してください。"

    data = json.loads(raw)
    stored_code = data["code"]
    attempts = data["attempts"]

    if input_code == stored_code:
        await r.delete(key)
        return True, "認証成功"

    # 失敗: 試行回数更新
    attempts += 1
    if attempts >= VERIFY_MAX_ATTEMPTS:
        await r.delete(key)
        await r.set(lock_key, "1", ex=VERIFY_LOCK_TTL)
        return False, "認証コードの試行回数が上限に達しました。30分後に再度お試しください。"

    data["attempts"] = attempts
    ttl = await r.ttl(key)
    if ttl > 0:
        await r.set(key, json.dumps(data), ex=ttl)
    return False, f"認証コードが正しくありません。残り{VERIFY_MAX_ATTEMPTS - attempts}回"


async def create_reset_token(r: aioredis.Redis, user_id: int) -> str:
    """パスワードリセットトークンを生成"""
    token = secrets.token_urlsafe(48)
    key = f"{RESET_TOKEN_PREFIX}{token}"
    await r.set(key, str(user_id), ex=RESET_TOKEN_TTL)
    return token


async def validate_reset_token(r: aioredis.Redis, token: str) -> Optional[int]:
    """リセットトークンを検証してuser_idを返す"""
    key = f"{RESET_TOKEN_PREFIX}{token}"
    user_id = await r.get(key)
    if user_id is None:
        return None
    await r.delete(key)
    return int(user_id)


async def create_password_change_token(r: aioredis.Redis, user_id: int) -> str:
    """パスワード変更用一時トークンを生成（認証コードとは別にセッション用）"""
    token = secrets.token_urlsafe(32)
    key = f"{PASSWORD_CHANGE_TOKEN_PREFIX}{token}"
    await r.set(key, str(user_id), ex=PASSWORD_CHANGE_TOKEN_TTL)
    return token


async def validate_password_change_token(r: aioredis.Redis, token: str) -> Optional[int]:
    """パスワード変更トークンを検証してuser_idを返す（トークンは削除しない）"""
    key = f"{PASSWORD_CHANGE_TOKEN_PREFIX}{token}"
    user_id = await r.get(key)
    if user_id is None:
        return None
    return int(user_id)


async def consume_password_change_token(r: aioredis.Redis, token: str) -> Optional[int]:
    """パスワード変更トークンを検証・消費してuser_idを返す"""
    key = f"{PASSWORD_CHANGE_TOKEN_PREFIX}{token}"
    user_id = await r.get(key)
    if user_id is None:
        return None
    await r.delete(key)
    return int(user_id)


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()
