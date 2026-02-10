"""Stripe Webhook ルーター"""
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import SessionLocal
from app.core.api_keys import get_stripe_webhook_secret
from app.services import stripe_service, subscription_service
from app.models.user import User
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.processed_stripe_event import ProcessedStripeEvent
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Stripe Webhook エンドポイント (CSRF免除、署名検証)"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.construct_webhook_event(
            payload, sig_header, get_stripe_webhook_secret()
        )
    except Exception as e:
        logger.error(f"Stripe webhook署名検証失敗: {e}")
        raise HTTPException(status_code=401, detail="Invalid signature")

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]

    db = SessionLocal()
    try:
        # 冪等性チェック: 同一イベントの重複処理を防止
        if _is_event_processed(db, event_id):
            logger.info(f"Stripe webhook重複スキップ: {event_id} ({event_type})")
            return {"received": True}

        if event_type == "checkout.session.completed":
            _handle_checkout_completed(db, data)
        elif event_type == "customer.subscription.created":
            _handle_subscription_created(db, data)
        elif event_type == "customer.subscription.updated":
            _handle_subscription_updated(db, data, event_id)
        elif event_type == "customer.subscription.deleted":
            _handle_subscription_deleted(db, data)
        elif event_type == "invoice.paid":
            _handle_invoice_paid(db, data)
        elif event_type == "invoice.payment_failed":
            _handle_invoice_payment_failed(db, data)
        else:
            logger.info(f"未処理のStripeイベント: {event_type}")
            return {"received": True}

        # 処理済みとして記録
        _record_processed_event(db, event_id, event_type)

    except Exception as e:
        logger.error(f"Stripe webhook処理エラー: {event_type} - {e}")
        raise
    finally:
        db.close()

    return {"received": True}


# =========================================================
# 冪等性ヘルパー
# =========================================================

def _is_event_processed(db: Session, event_id: str) -> bool:
    return db.query(ProcessedStripeEvent).filter(
        ProcessedStripeEvent.event_id == event_id
    ).first() is not None


def _record_processed_event(db: Session, event_id: str, event_type: str):
    db.add(ProcessedStripeEvent(event_id=event_id, event_type=event_type))
    db.commit()


# =========================================================
# イベントハンドラ
# =========================================================

def _handle_checkout_completed(db: Session, data: dict):
    """checkout.session.completed: Checkoutフローからの購読開始"""
    metadata = data.get("metadata", {})
    user_id = int(metadata.get("user_id", 0))
    plan_id = int(metadata.get("plan_id", 0))
    member_no = metadata.get("member_no", "")
    stripe_subscription_id = data.get("subscription")
    stripe_customer_id = data.get("customer")

    if not user_id or not plan_id:
        logger.warning(f"checkout.session.completed: metadata不足")
        return

    if not stripe_subscription_id:
        logger.warning(f"checkout.session.completed: subscription_id なし (無料プラン?)")
        return

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # Stripe Customer ID更新
        if stripe_customer_id and not user.stripe_customer_id:
            user.stripe_customer_id = stripe_customer_id
        # トライアル使用済みに (プランでトライアルが有効な場合のみ)
        plan = db.query(Plan).filter(Plan.id == plan_id).first()
        if plan and plan.trial_enabled:
            user.trial_used = True
        db.commit()

    # 購読レコード作成 (重複チェック)
    existing = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_subscription_id
    ).first()
    if existing:
        logger.info(f"Checkout完了: 購読は既に存在 user_id={user_id}, subscription_id={existing.id}")
        return

    # Stripe Subscriptionから正確なステータスと期間情報を取得
    status = "active"
    trial_end = None
    current_period_start = None
    current_period_end = None
    try:
        stripe_sub = stripe_service.retrieve_subscription(stripe_subscription_id)
        if stripe_sub:
            status = stripe_sub.get("status", "active")
            if stripe_sub.get("trial_end"):
                trial_end = datetime.fromtimestamp(stripe_sub["trial_end"])
            if stripe_sub.get("current_period_start"):
                current_period_start = datetime.fromtimestamp(stripe_sub["current_period_start"])
            if stripe_sub.get("current_period_end"):
                current_period_end = datetime.fromtimestamp(stripe_sub["current_period_end"])
            logger.info(f"Stripe Subscription取得: status={status}, trial_end={trial_end}")
    except Exception as e:
        logger.warning(f"Stripe Subscription取得失敗: {e}")

    subscription_service.create_subscription_record(
        db=db,
        user_id=user_id,
        plan_id=plan_id,
        member_no=member_no,
        stripe_subscription_id=stripe_subscription_id,
        status=status,
        trial_end=trial_end,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
    )

    logger.info(f"Checkout完了: user_id={user_id}, plan_id={plan_id}, status={status}")


def _handle_subscription_created(db: Session, data: dict):
    """customer.subscription.created: Billing Portal等からの新規サブスクリプション"""
    stripe_sub_id = data.get("id")
    stripe_customer_id = data.get("customer")
    status = data.get("status", "active")

    # 既存チェック (checkout.session.completed で作成済みの場合)
    existing = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub_id
    ).first()
    if existing:
        logger.info(f"subscription.created: 既存レコード stripe_sub_id={stripe_sub_id}")
        return

    # Customer ID → ユーザー逆引き
    user = db.query(User).filter(User.stripe_customer_id == stripe_customer_id).first()
    if not user:
        logger.warning(f"subscription.created: ユーザー不明 customer={stripe_customer_id}")
        return

    # Price ID → プラン逆引き
    items = data.get("items", {}).get("data", [])
    if not items:
        logger.warning(f"subscription.created: items なし stripe_sub_id={stripe_sub_id}")
        return

    price_id = items[0].get("price", {}).get("id")
    plan = db.query(Plan).filter(Plan.stripe_price_id == price_id).first()
    if not plan:
        logger.warning(f"subscription.created: プラン不明 price_id={price_id}")
        return

    # 期間情報取得
    trial_end = None
    current_period_start = None
    current_period_end = None
    if data.get("trial_end"):
        trial_end = datetime.fromtimestamp(data["trial_end"])
    if data.get("current_period_start"):
        current_period_start = datetime.fromtimestamp(data["current_period_start"])
    if data.get("current_period_end"):
        current_period_end = datetime.fromtimestamp(data["current_period_end"])

    subscription_service.create_subscription_record(
        db=db,
        user_id=user.id,
        plan_id=plan.id,
        member_no=user.member_no,
        stripe_subscription_id=stripe_sub_id,
        status=status,
        trial_end=trial_end,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
    )

    logger.info(f"subscription.created: レコード作成 user_id={user.id}, plan_id={plan.id}, status={status}")


def _handle_subscription_updated(db: Session, data: dict, event_id: str):
    """customer.subscription.updated: ステータス変更 + プラン変更検知"""
    stripe_sub_id = data.get("id")
    status = data.get("status", "active")
    cancel_at_period_end = data.get("cancel_at_period_end", False)

    period_start = data.get("current_period_start")
    period_end = data.get("current_period_end")
    trial_end = data.get("trial_end")

    # 1. 基本情報更新 (ステータス・期間)
    subscription_service.update_subscription_from_stripe(
        db=db,
        stripe_subscription_id=stripe_sub_id,
        status=status,
        cancel_at_period_end=cancel_at_period_end,
        current_period_start=datetime.fromtimestamp(period_start) if period_start else None,
        current_period_end=datetime.fromtimestamp(period_end) if period_end else None,
        trial_end=datetime.fromtimestamp(trial_end) if trial_end else None,
    )

    # 2. プラン変更検知 (items から現在のprice_idを取得)
    items = data.get("items", {}).get("data", [])
    if items:
        new_price_id = items[0].get("price", {}).get("id")
        if new_price_id:
            subscription_service.detect_and_handle_plan_change(
                db=db,
                stripe_subscription_id=stripe_sub_id,
                new_stripe_price_id=new_price_id,
                current_period_end=datetime.fromtimestamp(period_end) if period_end else None,
                stripe_event_id=event_id,
            )


def _handle_subscription_deleted(db: Session, data: dict):
    """customer.subscription.deleted"""
    stripe_sub_id = data.get("id")
    subscription_service.handle_subscription_deleted(db, stripe_sub_id)


def _handle_invoice_paid(db: Session, data: dict):
    """invoice.paid: 請求成功 → past_due から active への復帰"""
    subscription_id = data.get("subscription")
    if subscription_id:
        subscription_service.handle_invoice_paid(db, subscription_id)
    logger.info(f"請求成功: subscription={subscription_id}")


def _handle_invoice_payment_failed(db: Session, data: dict):
    """invoice.payment_failed: 決済失敗 → past_due + 配信停止"""
    subscription_id = data.get("subscription")
    if subscription_id:
        subscription_service.handle_payment_failed(db, subscription_id)
    logger.warning(f"決済失敗: subscription={subscription_id}")
