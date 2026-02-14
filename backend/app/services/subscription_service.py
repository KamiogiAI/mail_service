"""購読ビジネスロジック"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional
from datetime import datetime

from app.models.subscription import Subscription
from app.models.subscription_plan_change import SubscriptionPlanChange
from app.models.plan import Plan
from app.models.user import User
from app.models.service_setting import ServiceSetting
from app.models.promotion_code import PromotionCode
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
    """Stripe webhookからの購読更新 (ステータス・期間情報)"""
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


# =========================================================
# プラン変更検知・処理
# =========================================================

def detect_and_handle_plan_change(
    db: Session,
    stripe_subscription_id: str,
    new_stripe_price_id: str,
    current_period_end: datetime = None,
    stripe_event_id: str = None,
):
    """Stripe webhookからのプラン変更を検知し、アップグレード/ダウングレードを処理"""
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_subscription_id
    ).first()
    if not sub:
        return

    new_plan = db.query(Plan).filter(Plan.stripe_price_id == new_stripe_price_id).first()
    if not new_plan:
        logger.warning(f"プラン変更検知: 不明なprice_id={new_stripe_price_id}")
        return

    # 現在のplan_idと同じ → 変更なし (ダウングレード予約が残っていたらクリア)
    if new_plan.id == sub.plan_id:
        if sub.scheduled_plan_id:
            logger.info(f"プラン変更取消: subscription_id={sub.id}, 元のプランに戻りました")
            sub.scheduled_plan_id = None
            sub.scheduled_change_at = None
            # 未適用の変更履歴を取消
            _cancel_pending_plan_changes(db, sub.id)
            db.commit()
        return

    # 既にスケジュール済みの変更先と同じ → 何もしない
    if sub.scheduled_plan_id == new_plan.id:
        return

    old_plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
    old_price = old_plan.price if old_plan else 0
    new_price = new_plan.price

    if new_price >= old_price:
        # アップグレード or 同額: 即時適用
        change_type = "upgrade" if new_price > old_price else "lateral"
        _apply_plan_change_immediately(db, sub, old_plan, new_plan, change_type, stripe_event_id)
    else:
        # ダウングレード: 期間終了時に適用 (支払い済み期間は上位プランを維持)
        # current_period_endがNoneの場合、DBの値を使う
        effective_date = current_period_end or sub.current_period_end
        _schedule_plan_downgrade(db, sub, old_plan, new_plan, effective_date, stripe_event_id)
        # ダウングレードの場合、クーポン削除は実際の適用時(apply_scheduled_plan_changes)で行う


def _should_remove_coupon(db: Session, stripe_subscription_id: str, new_plan_id: int) -> bool:
    """クーポンを削除すべきか判定
    
    - クーポンが適用されていない → False
    - eligible_plan_ids が null（全プラン対象）→ False
    - eligible_plan_ids に新プランが含まれる → False
    - eligible_plan_ids に新プランが含まれない → True
    """
    discount_info = stripe_service.get_subscription_discount_info(stripe_subscription_id)
    stripe_coupon_id = discount_info.get("stripe_coupon_id")
    
    if not stripe_coupon_id:
        # クーポン適用なし
        return False
    
    # DBからPromotionCodeを検索
    promo = db.query(PromotionCode).filter(
        PromotionCode.stripe_coupon_id == stripe_coupon_id
    ).first()
    
    if not promo:
        # DBにないクーポン（手動適用など）→ 安全のため削除しない
        logger.warning(f"Unknown coupon {stripe_coupon_id}, skipping removal")
        return False
    
    if promo.eligible_plan_ids is None:
        # 全プラン対象 → 削除しない
        return False
    
    if new_plan_id in promo.eligible_plan_ids:
        # 新プランが対象に含まれる → 削除しない
        return False
    
    # 新プランが対象外 → 削除する
    logger.info(f"Coupon {stripe_coupon_id} not eligible for plan {new_plan_id}, will remove")
    return True


def _apply_plan_change_immediately(
    db: Session,
    sub: Subscription,
    old_plan: Plan,
    new_plan: Plan,
    change_type: str,
    stripe_event_id: str = None,
):
    """プラン変更を即時適用 (アップグレード・同額変更)"""
    old_plan_id = sub.plan_id
    sub.plan_id = new_plan.id
    sub.scheduled_plan_id = None
    sub.scheduled_change_at = None

    # 未適用のダウングレード予約があればキャンセル
    _cancel_pending_plan_changes(db, sub.id)

    # 変更履歴記録
    change = SubscriptionPlanChange(
        subscription_id=sub.id,
        old_plan_id=old_plan_id,
        new_plan_id=new_plan.id,
        change_type=change_type,
        applied=True,
        stripe_event_id=stripe_event_id,
    )
    db.add(change)
    db.commit()

    # 回答引き継ぎ
    if sub.user_id:
        migrate_answers_on_plan_change(db, sub.user_id, old_plan_id, new_plan.id)

    old_name = old_plan.name if old_plan else "不明"
    logger.info(
        f"プラン変更適用: subscription_id={sub.id}, "
        f"{old_name}(id={old_plan_id}) → {new_plan.name}(id={new_plan.id}) [{change_type}]"
    )

    # アップグレード時、新プランがクーポン対象外ならクーポンを削除
    if sub.stripe_subscription_id and _should_remove_coupon(db, sub.stripe_subscription_id, new_plan.id):
        if stripe_service.remove_subscription_coupon(sub.stripe_subscription_id):
            logger.info(f"アップグレードに伴いクーポン削除: subscription_id={sub.id}")
        else:
            logger.warning(f"クーポン削除失敗: subscription_id={sub.id}")


def _schedule_plan_downgrade(
    db: Session,
    sub: Subscription,
    old_plan: Plan,
    new_plan: Plan,
    period_end: datetime = None,
    stripe_event_id: str = None,
):
    """ダウングレードを期間終了時にスケジュール"""
    # 既存の未適用予約をキャンセル
    _cancel_pending_plan_changes(db, sub.id)

    sub.scheduled_plan_id = new_plan.id
    sub.scheduled_change_at = period_end

    change = SubscriptionPlanChange(
        subscription_id=sub.id,
        old_plan_id=sub.plan_id,
        new_plan_id=new_plan.id,
        change_type="downgrade",
        effective_at=period_end,
        applied=False,
        stripe_event_id=stripe_event_id,
    )
    db.add(change)
    db.commit()

    old_name = old_plan.name if old_plan else "不明"
    logger.info(
        f"ダウングレード予約: subscription_id={sub.id}, "
        f"{old_name} → {new_plan.name}, 適用予定={period_end}"
    )


def _cancel_pending_plan_changes(db: Session, subscription_id: int):
    """未適用のプラン変更履歴をキャンセル"""
    pending = db.query(SubscriptionPlanChange).filter(
        SubscriptionPlanChange.subscription_id == subscription_id,
        SubscriptionPlanChange.applied == False,
    ).all()
    for p in pending:
        p.applied = True  # 取消扱い (change_typeはそのまま残す)
    if pending:
        db.flush()


def apply_scheduled_plan_changes(db: Session, now: datetime):
    """期限到来したダウングレードを一括適用 (スケジューラから呼ばれる)"""
    subs = db.query(Subscription).filter(
        Subscription.scheduled_plan_id != None,
        Subscription.scheduled_change_at <= now,
        Subscription.status.in_(["trialing", "active", "past_due", "admin_added"]),
    ).all()

    for sub in subs:
        old_plan_id = sub.plan_id
        new_plan_id = sub.scheduled_plan_id

        sub.plan_id = new_plan_id
        sub.scheduled_plan_id = None
        sub.scheduled_change_at = None

        # 変更履歴を適用済みに更新
        pending_change = db.query(SubscriptionPlanChange).filter(
            SubscriptionPlanChange.subscription_id == sub.id,
            SubscriptionPlanChange.new_plan_id == new_plan_id,
            SubscriptionPlanChange.applied == False,
        ).first()
        if pending_change:
            pending_change.applied = True

        # 回答引き継ぎ
        if sub.user_id:
            migrate_answers_on_plan_change(db, sub.user_id, old_plan_id, new_plan_id)

        # ダウングレード適用時、新プランがクーポン対象外ならクーポンを削除
        if sub.stripe_subscription_id and _should_remove_coupon(db, sub.stripe_subscription_id, new_plan_id):
            if stripe_service.remove_subscription_coupon(sub.stripe_subscription_id):
                logger.info(f"ダウングレード適用に伴いクーポン削除: subscription_id={sub.id}")
            else:
                logger.warning(f"クーポン削除失敗: subscription_id={sub.id}")

        logger.info(f"ダウングレード適用: subscription_id={sub.id}, plan {old_plan_id} → {new_plan_id}")

    if subs:
        db.commit()

    return len(subs)


# =========================================================
# 回答引き継ぎ
# =========================================================

def migrate_answers_on_plan_change(db: Session, user_id: int, old_plan_id: int, new_plan_id: int):
    """プラン変更時に同一 var_name の回答を新プランの質問にコピー"""
    from app.models.plan_question import PlanQuestion
    from app.models.user_answer import UserAnswer

    old_questions = db.query(PlanQuestion).filter(PlanQuestion.plan_id == old_plan_id).all()
    new_questions = db.query(PlanQuestion).filter(PlanQuestion.plan_id == new_plan_id).all()

    # 旧プランの var_name → 回答値 マップ
    old_var_map = {}
    for q in old_questions:
        answer = db.query(UserAnswer).filter(
            UserAnswer.user_id == user_id,
            UserAnswer.question_id == q.id,
        ).first()
        if answer and answer.answer_value:
            old_var_map[q.var_name] = answer.answer_value

    if not old_var_map:
        return

    copied_count = 0
    for nq in new_questions:
        if nq.var_name not in old_var_map:
            continue
        existing = db.query(UserAnswer).filter(
            UserAnswer.user_id == user_id,
            UserAnswer.question_id == nq.id,
        ).first()
        if not existing:
            db.add(UserAnswer(
                user_id=user_id,
                question_id=nq.id,
                answer_value=old_var_map[nq.var_name],
            ))
            copied_count += 1

    if copied_count:
        db.commit()
        logger.info(f"回答引き継ぎ: user_id={user_id}, {old_plan_id} → {new_plan_id}, {copied_count}件コピー")


# =========================================================
# 既存: 削除・決済失敗・決済成功
# =========================================================

def handle_subscription_deleted(db: Session, stripe_subscription_id: str):
    """購読削除処理 (期限到来のダウングレード予約があれば先に適用)"""
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_subscription_id
    ).first()
    if not sub:
        return

    # ダウングレード予約が残っていれば、キャンセル前に適用
    if sub.scheduled_plan_id:
        old_plan_id = sub.plan_id
        new_plan_id = sub.scheduled_plan_id
        sub.plan_id = new_plan_id

        pending_change = db.query(SubscriptionPlanChange).filter(
            SubscriptionPlanChange.subscription_id == sub.id,
            SubscriptionPlanChange.new_plan_id == new_plan_id,
            SubscriptionPlanChange.applied == False,
        ).first()
        if pending_change:
            pending_change.applied = True

        logger.info(f"購読終了前にダウングレード適用: subscription_id={sub.id}, {old_plan_id} → {new_plan_id}")

    # プラン削除予約によるキャンセルの場合、終了メールを送信
    plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
    if plan and plan.pending_delete and sub.user_id:
        user = db.query(User).filter(User.id == sub.user_id).first()
        if user:
            send_subscription_cancel_email(user.email, f"{user.name_last} {user.name_first}", plan.name)
            logger.info(f"プラン終了メール送信: user_id={user.id}, plan={plan.name}")

    sub.status = "canceled"
    sub.scheduled_plan_id = None
    sub.scheduled_change_at = None
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
        sub.scheduled_plan_id = None
        sub.scheduled_change_at = None

        # 通知メール送信
        if sub.user_id:
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user:
                send_subscription_cancel_email(user.email, f"{user.name_last} {user.name_first}", plan.name)

    db.commit()


def schedule_cancel_plan_subscriptions(db: Session, plan_id: int):
    """プラン削除予約時: 全加入者の購読を解約予約（期間終了時にキャンセル）"""
    import time
    
    subs = db.query(Subscription).filter(
        Subscription.plan_id == plan_id,
        Subscription.status.in_(["trialing", "active", "past_due"]),
        Subscription.stripe_subscription_id != None,
    ).all()

    for sub in subs:
        try:
            stripe_service.cancel_subscription(sub.stripe_subscription_id, at_period_end=True)
            sub.cancel_at_period_end = True
        except Exception as e:
            logger.error(f"Stripe購読解約予約失敗: {sub.stripe_subscription_id} - {e}")
        
        # Resendレート制限対策: 少し間隔を空ける
        time.sleep(0.5)

    # admin_addedはStripe連携なしなので、即座にキャンセル扱い
    admin_subs = db.query(Subscription).filter(
        Subscription.plan_id == plan_id,
        Subscription.status == "admin_added",
    ).all()
    for sub in admin_subs:
        sub.status = "canceled"

    db.commit()
    logger.info(f"プラン削除予約: plan_id={plan_id}, 解約予約={len(subs)}件, admin_added即時終了={len(admin_subs)}件")


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
