"""スロットリング管理"""
import time
from app.core.redis import get_sync_redis
from app.core.logging import get_logger

logger = get_logger(__name__)

THROTTLE_KEY = "worker:throttle_extra"
BASE_SLEEP = 5  # 基本sleep秒数
THROTTLE_INCREMENT = 10  # 429時の追加秒数


def get_throttle_sleep() -> int:
    """現在のスロットリング秒数を取得"""
    redis = get_sync_redis()
    extra = redis.get(THROTTLE_KEY)
    return BASE_SLEEP + (int(extra) if extra else 0)


def increase_throttle():
    """スロットリングを増加 (Resend 429時)"""
    redis = get_sync_redis()
    current = redis.get(THROTTLE_KEY)
    new_val = (int(current) if current else 0) + THROTTLE_INCREMENT
    redis.set(THROTTLE_KEY, str(new_val), ex=600)  # 10分TTL
    logger.warning(f"スロットリング増加: {new_val}秒")


def reset_throttle():
    """スロットリングリセット"""
    redis = get_sync_redis()
    redis.delete(THROTTLE_KEY)


def check_emergency_stop() -> bool:
    """緊急停止フラグチェック"""
    redis = get_sync_redis()
    return bool(redis.get("emergency_stop"))


def set_emergency_stop(active: bool):
    """緊急停止フラグ設定"""
    redis = get_sync_redis()
    if active:
        redis.set("emergency_stop", "1")
    else:
        redis.delete("emergency_stop")
