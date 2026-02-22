"""メール履歴サービス

ユーザーへの送信メールを履歴として保存し、
ユーザー×プランごとに最新1件のみ保持する。
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.models.user_email_history import UserEmailHistory
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")

# 保持する履歴の最大件数（プランごと）
MAX_HISTORY_PER_USER_PLAN = 1


def save_email_history(
    db: Session,
    user_id: int,
    plan_id: int,
    delivery_id: int | None,
    subject: str,
    body_html: str,
) -> None:
    """
    メール履歴を保存し、1件を超えた古い履歴を削除する。
    
    Args:
        db: DBセッション
        user_id: ユーザーID
        plan_id: プランID
        delivery_id: 配信ID
        subject: メール件名
        body_html: メール本文（HTML）
    """
    now = datetime.now(JST)
    
    # 履歴を挿入
    history = UserEmailHistory(
        user_id=user_id,
        plan_id=plan_id,
        delivery_id=delivery_id,
        subject=subject,
        body_html=body_html,
        sent_at=now,
    )
    db.add(history)
    db.flush()
    
    # 1件を超えた古い履歴を削除
    _cleanup_old_history(db, user_id, plan_id)


def _cleanup_old_history(db: Session, user_id: int, plan_id: int) -> None:
    """1件を超えた古い履歴を削除"""
    old_ids = db.query(UserEmailHistory.id).filter(
        UserEmailHistory.user_id == user_id,
        UserEmailHistory.plan_id == plan_id,
    ).order_by(UserEmailHistory.sent_at.desc()).offset(MAX_HISTORY_PER_USER_PLAN).all()
    
    if old_ids:
        ids_to_delete = [x[0] for x in old_ids]
        db.query(UserEmailHistory).filter(
            UserEmailHistory.id.in_(ids_to_delete)
        ).delete(synchronize_session=False)
        logger.debug(f"古いメール履歴を削除: user_id={user_id}, plan_id={plan_id}, count={len(ids_to_delete)}")
