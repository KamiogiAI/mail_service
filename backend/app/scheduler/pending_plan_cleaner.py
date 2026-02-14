"""削除予約済みプランのクリーンアップ"""
from app.core.database import SessionLocal
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.core.logging import get_logger

logger = get_logger(__name__)

ACTIVE_STATUSES = ("trialing", "active", "past_due", "admin_added")


def cleanup_pending_delete_plans():
    """全購読が終了した削除予約プランを物理削除"""
    db = SessionLocal()
    try:
        # pending_delete=Trueのプランを取得
        pending_plans = db.query(Plan).filter(Plan.pending_delete == True).all()
        
        for plan in pending_plans:
            # アクティブな購読があるかチェック
            active_count = db.query(Subscription).filter(
                Subscription.plan_id == plan.id,
                Subscription.status.in_(ACTIVE_STATUSES),
            ).count()
            
            if active_count == 0:
                # 全購読が終了 → プランを物理削除
                logger.info(f"削除予約プラン物理削除: plan_id={plan.id}, name={plan.name}")
                db.delete(plan)
        
        db.commit()
        
    except Exception as e:
        logger.error(f"削除予約プランクリーンアップエラー: {e}")
    finally:
        db.close()
