from fastapi import APIRouter
from app.core.database import check_db_connection
from app.core.redis import check_redis_connection

router = APIRouter()


@router.get("/health")
@router.get("/api/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    db_ok = check_db_connection()
    redis_ok = await check_redis_connection()

    status = "ok" if (db_ok and redis_ok) else "degraded"

    return {
        "status": status,
        "db": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
    }
