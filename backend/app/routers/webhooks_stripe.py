"""Stripe Webhook ルーター"""
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import SessionLocal
from app.core.api_keys import get_stripe_webhook_secret
from app.services import stripe_service, subscription_service
from app.services.mail_service import (
    send_subscription_welcome_email,
    send_plan_change_email,
    send_renewal_complete_email,
)
from app.models.user import User
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.processed_stripe_event import ProcessedStripeEvent
from app.models.promotion_code import PromotionCode
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")

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
    previous_attributes = event["data"].get("previous_attributes", {})

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
            _handle_subscription_updated(db, data, event_id, previous_attributes)
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
        # 既存レコードがincomplete等の場合は正しいステータスに更新
        if existing.status in ("incomplete", "incomplete_expired"):
            try:
                stripe_sub = stripe_service.retrieve_subscription(stripe_subscription_id)
                if stripe_sub:
                    existing.status = stripe_sub.get("status", "active")
                    if stripe_sub.get("trial_end"):
                        existing.trial_end = datetime.fromtimestamp(stripe_sub["trial_end"])
                    if stripe_sub.get("current_period_start"):
                        existing.current_period_start = datetime.fromtimestamp(stripe_sub["current_period_start"])
                    if stripe_sub.get("current_period_end"):
                        existing.current_period_end = datetime.fromtimestamp(stripe_sub["current_period_end"])
                    db.commit()
                    logger.info(f"Checkout完了: 既存購読を更新 subscription_id={existing.id}, status={existing.status}")
            except Exception as e:
                logger.warning(f"Checkout完了: 既存購読の更新失敗: {e}")
        else:
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

    # プロモーションコード使用数を更新
    try:
        # Checkout Sessionのdiscounts配列からpromotion_codeを取得
        discounts = data.get("discounts", []) or []
        # または単一のdiscount
        if not discounts and data.get("discount"):
            discount = data.get("discount", {})
            if discount.get("promotion_code"):
                discounts = [{"promotion_code": discount["promotion_code"]}]
        
        for discount_item in discounts:
            promo_code_id = discount_item.get("promotion_code")
            if promo_code_id:
                promo = db.query(PromotionCode).filter(
                    PromotionCode.stripe_promotion_code_id == promo_code_id
                ).first()
                if promo:
                    promo.times_redeemed = (promo.times_redeemed or 0) + 1
                    db.commit()
                    logger.info(f"プロモーションコード使用: code={promo.code}, times_redeemed={promo.times_redeemed}")
    except Exception as e:
        logger.warning(f"プロモーションコード使用数更新失敗: {e}")
    
    # 加入完了メール送信
    if user and plan:
        is_trial = status == "trialing"
        next_date = trial_end if is_trial else current_period_end
        next_date_str = next_date.astimezone(JST).strftime("%Y年%m月%d日") if next_date else "-"
        trial_end_str = trial_end.astimezone(JST).strftime("%Y年%m月%d日") if trial_end else None
        
        send_subscription_welcome_email(
            to_email=user.email,
            name=f"{user.name_last} {user.name_first}",
            plan_name=plan.name,
            plan_price=plan.price,
            next_billing_date=next_date_str,
            is_trial=is_trial,
            trial_end_date=trial_end_str,
        )


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
    
    # 加入完了メール送信
    is_trial = status == "trialing"
    next_date = trial_end if is_trial else current_period_end
    next_date_str = next_date.astimezone(JST).strftime("%Y年%m月%d日") if next_date else "-"
    trial_end_str = trial_end.astimezone(JST).strftime("%Y年%m月%d日") if trial_end else None
    
    send_subscription_welcome_email(
        to_email=user.email,
        name=f"{user.name_last} {user.name_first}",
        plan_name=plan.name,
        plan_price=plan.price,
        next_billing_date=next_date_str,
        is_trial=is_trial,
        trial_end_date=trial_end_str,
    )


def _handle_subscription_updated(db: Session, data: dict, event_id: str, previous_attributes: dict = None):
    """customer.subscription.updated: ステータス変更 + プラン変更検知"""
    previous_attributes = previous_attributes or {}
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

    # 3. プロモーションコード使用数を更新（新規適用時のみ）
    # previous_attributes に "discount" が含まれている = 今回 discount が変更された
    try:
        if "discount" in previous_attributes:
            discount = data.get("discount")
            if discount and discount.get("promotion_code"):
                promo_code_id = discount["promotion_code"]
                promo = db.query(PromotionCode).filter(
                    PromotionCode.stripe_promotion_code_id == promo_code_id
                ).first()
                if promo:
                    promo.times_redeemed = (promo.times_redeemed or 0) + 1
                    db.commit()
                    logger.info(f"プロモーションコード使用（プラン変更）: code={promo.code}, times_redeemed={promo.times_redeemed}")
    except Exception as e:
        logger.warning(f"プロモーションコード使用数更新失敗（subscription.updated）: {e}")


def _handle_subscription_deleted(db: Session, data: dict):
    """customer.subscription.deleted"""
    stripe_sub_id = data.get("id")
    subscription_service.handle_subscription_deleted(db, stripe_sub_id)


def _handle_invoice_paid(db: Session, data: dict):
    """invoice.paid: 請求成功 → past_due から active への復帰 + 初回課金時にtrial_used設定 + 更新完了メール"""
    subscription_id = data.get("subscription")
    if subscription_id:
        subscription_service.handle_invoice_paid(db, subscription_id)

    # 有料課金が発生した場合、ユーザーのtrial_usedをTrueに設定
    # (トライアルなしプランからトライアルありプランへの乗り換え防止)
    amount_paid = data.get("amount_paid", 0)
    customer_id = data.get("customer")
    billing_reason = data.get("billing_reason", "")
    
    if amount_paid > 0 and customer_id:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user and not user.trial_used:
            user.trial_used = True
            db.commit()
            logger.info(f"初回課金完了: user_id={user.id}, trial_used=True に設定")
        
        # 更新完了メール送信（初回以外の請求時）
        # billing_reason: subscription_cycle（定期更新）, subscription_update（変更時の日割り）
        if user and subscription_id and billing_reason == "subscription_cycle":
            sub = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            if sub:
                plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
                if plan:
                    next_date = sub.current_period_end
                    next_date_str = next_date.astimezone(JST).strftime("%Y年%m月%d日") if next_date else "-"
                    send_renewal_complete_email(
                        to_email=user.email,
                        name=f"{user.name_last} {user.name_first}",
                        plan_name=plan.name,
                        amount=amount_paid,
                        next_billing_date=next_date_str,
                    )

    logger.info(f"請求成功: subscription={subscription_id}, amount_paid={amount_paid}")


def _handle_invoice_payment_failed(db: Session, data: dict):
    """invoice.payment_failed: 決済失敗 → past_due + 配信停止"""
    subscription_id = data.get("subscription")
    if subscription_id:
        subscription_service.handle_payment_failed(db, subscription_id)
    logger.warning(f"決済失敗: subscription={subscription_id}")
