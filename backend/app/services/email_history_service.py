"""メール履歴サービス

ユーザーへの送信メールを履歴として保存し、
ユーザー×プランごとに最新10件のみ保持する。
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.models.user_email_history import UserEmailHistory
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")

# 保持する履歴の最大件数
MAX_HISTORY_PER_USER_PLAN = 10


def save_email_history(
    db: Session,
    user_id: int,
    plan_id: int | None,
    delivery_id: int | None,
    subject: str,
    body_html: str,
) -> None:
    """
    メール履歴を保存し、10件を超えた古い履歴を削除する。
    
    Args:
        db: DBセッション
        user_id: ユーザーID
        plan_id: プランID（手動送信の場合はNone）
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
    db.flush()  # IDを確定
    
    # 10件を超えた古い履歴を削除
    _cleanup_old_history(db, user_id, plan_id)


def _cleanup_old_history(db: Session, user_id: int, plan_id: int | None) -> None:
    """10件を超えた古い履歴を削除"""
    # plan_idがNULLの場合とそれ以外でフィルタ条件を分ける
    if plan_id is not None:
        filter_cond = (UserEmailHistory.plan_id == plan_id)
    else:
        filter_cond = (UserEmailHistory.plan_id.is_(None))
    
    # 10件目以降のIDを取得
    old_ids = db.query(UserEmailHistory.id).filter(
        UserEmailHistory.user_id == user_id,
        filter_cond,
    ).order_by(UserEmailHistory.sent_at.desc()).offset(MAX_HISTORY_PER_USER_PLAN).all()
    
    if old_ids:
        ids_to_delete = [x[0] for x in old_ids]
        db.query(UserEmailHistory).filter(
            UserEmailHistory.id.in_(ids_to_delete)
        ).delete(synchronize_session=False)
        logger.debug(f"古いメール履歴を削除: user_id={user_id}, plan_id={plan_id}, count={len(ids_to_delete)}")
