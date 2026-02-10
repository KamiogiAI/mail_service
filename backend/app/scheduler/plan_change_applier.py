"""期限到来したダウングレード予約の適用"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import SessionLocal
from app.services.subscription_service import apply_scheduled_plan_changes
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def apply_pending_plan_changes():
    """スケジューラから呼ばれる: 期限到来したダウングレードを適用"""
    now = datetime.now(JST)
    db = SessionLocal()
    try:
        count = apply_scheduled_plan_changes(db, now)
        if count > 0:
            logger.info(f"ダウングレード適用完了: {count}件")
    except Exception as e:
        logger.error(f"ダウングレード適用エラー: {e}")
    finally:
        db.close()
