import redis.asyncio as aioredis
import redis as sync_redis
from app.core.config import settings

# 非同期Redis (FastAPI用)
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=20,
    decode_responses=True,
)


async def get_redis() -> aioredis.Redis:
    """FastAPI依存関数: 非同期Redisクライアント取得"""
    return aioredis.Redis(connection_pool=redis_pool)


# 同期Redis (Worker/Scheduler用)
sync_redis_pool = sync_redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=10,
    decode_responses=True,
)


def get_sync_redis() -> sync_redis.Redis:
    """同期Redisクライアント取得"""
    return sync_redis.Redis(connection_pool=sync_redis_pool)


async def check_redis_connection() -> bool:
    """Redis接続チェック"""
    try:
        r = await get_redis()
        await r.ping()
        return True
    except Exception:
        return False
