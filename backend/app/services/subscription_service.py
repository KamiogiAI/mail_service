"""購読ビジネスロジック"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional
from datetime import datetime

from app.models.subscription import Subscription
from app.models.plan import Plan
from app.models.user import User
from app.models.service_setting import ServiceSetting
from app.services import stripe_service
from app.services.mail_service import send_subscription_cancel_email, send_payment_failed_email
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_active_subscriptions(db: Session, user_id: int) -> list[Subscription]:
    """アクティブな購読一覧"""
    return db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.status.in_(["trialing", "active", "past_due", "admin_added"]),
    ).all()


def has_active_subscription(db: Session, user_id: int) -> bool:
    """アクティブな購読があるか"""
    return db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.status.in_(["trialing", "active", "past_due", "admin_added"]),
    ).count() > 0


def has_plan_subscription(db: Session, user_id: int, plan_id: int) -> bool:
    """特定プランの購読があるか"""
    return db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.plan_id == plan_id,
        Subscription.status.in_(["trialing", "active", "past_due", "admin_added"]),
    ).count() > 0


def check_multiple_plan_allowed(db: Session) -> bool:
    """複数プラン同時加入が許可されているか"""
    setting = db.query(ServiceSetting).first()
    if setting:
        return setting.allow_multiple_plans
    return False


def create_subscription_record(
    db: Session,
    user_id: int,
    plan_id: int,
    member_no: str,
    stripe_subscription_id: str = None,
    status: str = "active",
    trial_end: datetime = None,
    current_period_start: datetime = None,
    current_period_end: datetime = None,
) -> Subscription:
    """購読レコード作成"""
    sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        member_no_snapshot=member_no,
        stripe_subscription_id=stripe_subscription_id,
        status=status,
        trial_end=trial_end,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def update_subscription_from_stripe(
    db: Session,
    stripe_subscription_id: str,
    status: str,
    cancel_at_period_end: bool = False,
    current_period_start: datetime = None,
    current_period_end: datetime = None,
    trial_end: datetime = None,
):
    """Stripe webhookからの購読更新"""
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_subscription_id
    ).first()
    if not sub:
        logger.warning(f"購読が見つかりません: stripe_subscription_id={stripe_subscription_id}")
        return

    sub.status = status
    sub.cancel_at_period_end = cancel_at_period_end
    if current_period_start:
        sub.current_period_start = current_period_start
    if current_period_end:
        sub.current_period_end = current_period_end
    if trial_end:
        sub.trial_end = trial_end
    db.commit()


def handle_subscription_deleted(db: Session, stripe_subscription_id: str):
    """購読削除処理"""
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_subscription_id
    ).first()
    if not sub:
        return
    sub.status = "canceled"
    db.commit()
    logger.info(f"購読終了: subscription_id={sub.id}")


def force_cancel_plan_subscriptions(db: Session, plan_id: int):
    """プラン削除時: 全加入者の購読を強制解約"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        return

    subs = db.query(Subscription).filter(
        Subscription.plan_id == plan_id,
        Subscription.status.in_(["trialing", "active", "past_due", "admin_added"]),
    ).all()

    for sub in subs:
        if sub.stripe_subscription_id:
            try:
                stripe_service.cancel_subscription_immediately(sub.stripe_subscription_id)
            except Exception as e:
                logger.error(f"Stripe購読解約失敗: {sub.stripe_subscription_id} - {e}")
        sub.status = "canceled"

        # 通知メール送信
        if sub.user_id:
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user:
                send_subscription_cancel_email(user.email, f"{user.name_last} {user.name_first}", plan.name)

    db.commit()


def handle_payment_failed(db: Session, stripe_subscription_id: str):
    """決済失敗 → past_due + 通知"""
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_subscription_id
    ).first()
    if not sub:
        return

    sub.status = "past_due"
    db.commit()

    if sub.user_id:
        user = db.query(User).filter(User.id == sub.user_id).first()
        plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
        if user and plan:
            send_payment_failed_email(
                user.email,
                f"{user.name_last} {user.name_first}",
                plan.name,
            )


def handle_invoice_paid(db: Session, stripe_subscription_id: str):
    """決済成功 → active に復帰 (past_due からの復帰)"""
    if not stripe_subscription_id:
        return

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_subscription_id
    ).first()
    if not sub:
        return

    # past_due または trialing から active への復帰
    if sub.status in ("past_due", "trialing"):
        old_status = sub.status
        sub.status = "active"
        db.commit()
        logger.info(f"購読復帰: subscription_id={sub.id}, {old_status} -> active")
