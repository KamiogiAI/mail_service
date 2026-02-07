import secrets
import json
import time
from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

SESSION_PREFIX = "session:"
SESSION_TTL = settings.SESSION_TIMEOUT_MINUTES * 60  # 秒


async def create_session(
    r: aioredis.Redis,
    user_id: int,
    role: str,
    member_no: str,
    email: str,
) -> str:
    """新しいセッションを作成し、session_idを返す"""
    session_id = secrets.token_hex(32)
    key = f"{SESSION_PREFIX}{session_id}"
    data = {
        "user_id": str(user_id),
        "role": role,
        "member_no": member_no,
        "email": email,
        "created_at": str(int(time.time())),
        "last_accessed": str(int(time.time())),
    }
    await r.hset(key, mapping=data)
    await r.expire(key, SESSION_TTL)
    return session_id


async def get_session(r: aioredis.Redis, session_id: str) -> Optional[dict]:
    """セッション情報を取得。アクセスごとにTTL更新"""
    if not session_id:
        return None
    key = f"{SESSION_PREFIX}{session_id}"
    data = await r.hgetall(key)
    if not data:
        return None
    # TTL更新 (アイドルタイムアウトリセット)
    await r.expire(key, SESSION_TTL)
    await r.hset(key, "last_accessed", str(int(time.time())))
    return data


async def destroy_session(r: aioredis.Redis, session_id: str) -> None:
    """セッションを破棄"""
    if session_id:
        await r.delete(f"{SESSION_PREFIX}{session_id}")


async def refresh_session_id(
    r: aioredis.Redis, old_session_id: str
) -> Optional[str]:
    """セッション固定化攻撃対策: 新しいsession_idに移行"""
    old_key = f"{SESSION_PREFIX}{old_session_id}"
    data = await r.hgetall(old_key)
    if not data:
        return None
    new_session_id = secrets.token_hex(32)
    new_key = f"{SESSION_PREFIX}{new_session_id}"
    await r.hset(new_key, mapping=data)
    await r.expire(new_key, SESSION_TTL)
    await r.delete(old_key)
    return new_session_id


async def invalidate_user_sessions(
    r: aioredis.Redis,
    user_id: int,
    exclude_session_id: Optional[str] = None,
) -> int:
    """
    指定ユーザーの全セッションを無効化する。

    Args:
        r: Redis接続
        user_id: 無効化対象のユーザーID
        exclude_session_id: 除外するセッションID（現在のセッションを維持する場合）

    Returns:
        削除したセッション数
    """
    deleted_count = 0
    user_id_str = str(user_id)
    cursor = 0

    while True:
        cursor, keys = await r.scan(cursor, match=f"{SESSION_PREFIX}*", count=100)
        for key in keys:
            # セッションIDを抽出
            session_id = key.replace(SESSION_PREFIX, "") if isinstance(key, str) else key.decode().replace(SESSION_PREFIX, "")

            # 除外対象ならスキップ
            if exclude_session_id and session_id == exclude_session_id:
                continue

            # セッションのuser_idを確認
            session_user_id = await r.hget(key, "user_id")
            if session_user_id:
                # bytes の場合はデコード
                if isinstance(session_user_id, bytes):
                    session_user_id = session_user_id.decode()
                if session_user_id == user_id_str:
                    await r.delete(key)
                    deleted_count += 1

        if cursor == 0:
            break

    return deleted_count
