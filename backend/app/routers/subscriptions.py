"""購読ルーター: Subscribe, Billing Portal, Checkout Complete"""
import urllib.parse
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.config import settings
from app.models.plan import Plan
from app.models.user import User
from app.models.promotion_code import PromotionCode
from app.models.subscription import Subscription
from app.schemas.subscription import (
    SubscribeRequest, BillingPortalRequest, SubscriptionInfo, CheckoutCompleteRequest,
)
from app.services import stripe_service, subscription_service
from app.routers.deps import require_login
from app.core.logging import get_logger

router = APIRouter(prefix="/api", tags=["subscriptions"])
logger = get_logger(__name__)


def _validate_redirect_url(url: str) -> str:
    """リダイレクトURLの安全性を検証 (同一オリジンのみ許可)"""
    if not url:
        return url
    parsed = urllib.parse.urlparse(url)
    site_parsed = urllib.parse.urlparse(settings.SITE_URL)
    if parsed.netloc and parsed.netloc != site_parsed.netloc:
        raise HTTPException(status_code=400, detail="不正なリダイレクトURLです")
    return url


@router.post("/subscribe")
async def subscribe(
    req: SubscribeRequest,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """購読開始 (Stripe Checkout Session作成)"""
    plan = db.query(Plan).filter(Plan.id == req.plan_id, Plan.is_active == True).first()
    if not plan:
        raise HTTPException(status_code=404, detail="プランが見つかりません")

    # 同じプランの重複購読チェック
    if subscription_service.has_plan_subscription(db, user.id, plan.id):
        raise HTTPException(status_code=400, detail="既にこのプランに加入しています")

    # 複数プラン制御
    if not subscription_service.check_multiple_plan_allowed(db):
        if subscription_service.has_active_subscription(db, user.id):
            raise HTTPException(
                status_code=400,
                detail="複数プランへの同時加入はできません。プラン変更をご利用ください。"
            )

    # プロモーションコード検証
    stripe_promotion_code_id = None
    if req.promotion_code:
        promo = db.query(PromotionCode).filter(
            PromotionCode.code == req.promotion_code,
        ).first()
        if not promo:
            raise HTTPException(status_code=400, detail="プロモーションコードが見つかりません")
        if not promo.is_active:
            raise HTTPException(status_code=400, detail="このプロモーションコードは無効です")
        if promo.expires_at and promo.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(status_code=400, detail="このプロモーションコードは有効期限切れです")
        if promo.max_redemptions and promo.times_redeemed >= promo.max_redemptions:
            raise HTTPException(status_code=400, detail="このプロモーションコードは使用回数の上限に達しています")
        # eligible_plan_idsはJSON型のため、int/strの混在を考慮して比較
        if promo.eligible_plan_ids and plan.id not in [int(pid) for pid in promo.eligible_plan_ids]:
            raise HTTPException(status_code=400, detail="このプロモーションコードはこのプランには適用できません")
        stripe_promotion_code_id = promo.stripe_promotion_code_id

    # 無料プラン: Stripe不要、直接購読作成
    if plan.price == 0:
        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            member_no_snapshot=user.member_no,
            status="active",
        )
        db.add(sub)
        db.commit()
        return {"message": "購読を開始しました", "subscription_id": sub.id}

    # 有料プラン: Stripe Checkout
    if not plan.stripe_price_id:
        raise HTTPException(status_code=400, detail="このプランは購読できません")

    # Stripe Customer作成 (未作成の場合)
    if not user.stripe_customer_id:
        try:
            customer_id = stripe_service.create_customer(
                email=user.email,
                name=f"{user.name_last} {user.name_first}",
                metadata={"user_id": str(user.id), "member_no": user.member_no},
            )
        except Exception as e:
            logger.error(f"Stripe Customer作成失敗: user_id={user.id}, error={e}")
            raise HTTPException(status_code=500, detail="決済システムとの連携に失敗しました")
        user.stripe_customer_id = customer_id
        db.commit()

    # トライアル判定 (プランごとの設定 + ユーザーの使用済みフラグ)
    trial_days = 30 if (plan.trial_enabled and not user.trial_used) else None

    # リダイレクトURL検証 (オープンリダイレクト防止)
    success_url = _validate_redirect_url(req.success_url) or (
        f"{settings.SITE_URL}/user/mypage.html?subscription=success&session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = _validate_redirect_url(req.cancel_url) or (
        f"{settings.SITE_URL}/user/subscribe.html?plan_id={plan.id}"
    )

    try:
        checkout_url = stripe_service.create_checkout_session(
            price_id=plan.stripe_price_id,
            customer_id=user.stripe_customer_id,
            customer_email=None,
            trial_days=trial_days,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": str(user.id),
                "plan_id": str(plan.id),
                "member_no": user.member_no,
            },
            stripe_promotion_code_id=stripe_promotion_code_id,
        )
    except Exception as e:
        logger.error(f"Stripe Checkout Session作成失敗: user_id={user.id}, plan_id={plan.id}, error={e}")
        raise HTTPException(status_code=500, detail="決済ページの作成に失敗しました")

    return {"checkout_url": checkout_url}


@router.post("/checkout-complete")
async def checkout_complete(
    req: CheckoutCompleteRequest,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Stripe Checkout完了後の購読レコード作成 (Webhookより先に到達した場合の補完)"""
    try:
        session = stripe_service.retrieve_checkout_session(req.session_id)
    except Exception as e:
        logger.warning(f"Checkout Session取得失敗: {e}")
        raise HTTPException(status_code=400, detail="セッション情報の取得に失敗しました")

    # metadataのuser_idとログインユーザー照合
    session_user_id = session.metadata.get("user_id") if session.metadata else None
    if session_user_id != str(user.id):
        raise HTTPException(status_code=403, detail="セッション情報が一致しません")

    # 完了済みセッションのみ処理
    if session.status != "complete":
        raise HTTPException(status_code=400, detail="決済が完了していません")

    stripe_sub = session.subscription
    if not stripe_sub:
        raise HTTPException(status_code=400, detail="購読情報が見つかりません")

    # stripe_subscription_idを取得 (expandされたオブジェクトまたはID文字列)
    stripe_sub_id = stripe_sub.id if hasattr(stripe_sub, "id") else str(stripe_sub)

    # Webhook既処理チェック (重複作成防止)
    existing = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub_id,
    ).first()
    if existing:
        return {"message": "購読は既に登録済みです", "subscription_id": existing.id}

    # 購読レコード作成
    plan_id = int(session.metadata.get("plan_id")) if session.metadata.get("plan_id") else None
    member_no = session.metadata.get("member_no", "")

    # Stripe Subscriptionから期間情報を取得
    trial_end = None
    current_period_start = None
    current_period_end = None
    status = "active"
    if hasattr(stripe_sub, "status"):
        status = stripe_sub.status
        if stripe_sub.trial_end:
            trial_end = datetime.fromtimestamp(stripe_sub.trial_end)
        if stripe_sub.current_period_start:
            current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start)
        if stripe_sub.current_period_end:
            current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)

    try:
        sub = subscription_service.create_subscription_record(
            db=db,
            user_id=user.id,
            plan_id=plan_id,
            member_no=member_no,
            stripe_subscription_id=stripe_sub_id,
            status=status,
            trial_end=trial_end,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
        )
    except IntegrityError:
        # Webhook が同時に作成した場合 (stripe_subscription_id UNIQUE制約)
        db.rollback()
        existing = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_sub_id,
        ).first()
        if existing:
            return {"message": "購読は既に登録済みです", "subscription_id": existing.id}
        raise HTTPException(status_code=500, detail="購読の作成に失敗しました")

    # トライアル使用フラグ更新
    if status == "trialing" and not user.trial_used:
        user.trial_used = True
        db.commit()

    logger.info(f"checkout-complete: 購読作成 user_id={user.id}, subscription_id={sub.id}")
    return {"message": "購読を登録しました", "subscription_id": sub.id}


@router.post("/billing-portal")
async def billing_portal(
    req: BillingPortalRequest,
    user: User = Depends(require_login),
):
    """Stripe Billing Portal"""
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="決済情報が見つかりません")

    return_url = req.return_url or f"{settings.SITE_URL}/user/mypage.html"
    try:
        url = stripe_service.create_billing_portal_session(user.stripe_customer_id, return_url)
    except Exception as e:
        logger.error(f"Stripe Billing Portal作成失敗: user_id={user.stripe_customer_id}, error={e}")
        raise HTTPException(status_code=500, detail="決済ポータルの作成に失敗しました")
    return {"portal_url": url}


@router.get("/my-subscriptions", response_model=list[SubscriptionInfo])
async def my_subscriptions(
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """自分の購読一覧"""
    subs = subscription_service.get_active_subscriptions(db, user.id)
    result = []
    for sub in subs:
        plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
        plan_price = plan.price if plan else 0

        # ダウングレード予約がある場合、予約先プラン名を取得
        scheduled_plan_name = None
        if sub.scheduled_plan_id:
            scheduled_plan = db.query(Plan).filter(Plan.id == sub.scheduled_plan_id).first()
            scheduled_plan_name = scheduled_plan.name if scheduled_plan else None

        # Stripeから割引情報を取得
        discount_name = None
        discount_percent = None
        discount_amount = None
        actual_price = plan_price

        if sub.stripe_subscription_id:
            try:
                discount_info = stripe_service.get_subscription_discount_info(sub.stripe_subscription_id)
                discount_name = discount_info.get("discount_name")
                discount_percent = discount_info.get("discount_percent")
                discount_amount = discount_info.get("discount_amount")

                # 実際の請求額を計算
                if discount_percent:
                    actual_price = int(plan_price * (100 - discount_percent) / 100)
                elif discount_amount:
                    actual_price = max(0, plan_price - discount_amount)
            except Exception:
                pass  # Stripe取得失敗時は定価を使用

        info = SubscriptionInfo(
            id=sub.id,
            plan_id=sub.plan_id,
            plan_name=plan.name if plan else None,
            plan_price=plan_price,
            status=sub.status,
            cancel_at_period_end=sub.cancel_at_period_end,
            current_period_end=sub.current_period_end,
            trial_end=sub.trial_end,
            scheduled_plan_name=scheduled_plan_name,
            scheduled_change_at=sub.scheduled_change_at,
            discount_name=discount_name,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            actual_price=actual_price,
        )
        result.append(info)
    return result


@router.post("/cancel-subscription/{subscription_id}")
async def cancel_subscription(
    subscription_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """購読解約 (期間終了まで継続)"""
    sub = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.user_id == user.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="購読が見つかりません")

    if sub.stripe_subscription_id:
        try:
            stripe_service.cancel_subscription(sub.stripe_subscription_id, at_period_end=True)
        except Exception as e:
            logger.error(f"Stripe購読解約失敗: subscription_id={sub.stripe_subscription_id}, error={e}")
            raise HTTPException(status_code=500, detail="解約処理に失敗しました")
    sub.cancel_at_period_end = True
    db.commit()

    return {"message": "解約予約しました。期間終了まで引き続きご利用いただけます。"}
