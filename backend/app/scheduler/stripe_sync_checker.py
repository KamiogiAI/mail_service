"""日次: Stripe⇔DB整合性チェック"""
import stripe
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.api_keys import get_stripe_secret_key
from app.models.subscription import Subscription
from app.models.user import User
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def check_stripe_db_consistency():
    """Stripeとデータベースの整合性をチェック
    
    日次で実行し、不一致があればログに記録する。
    自動修正は行わず、検出のみ。
    """
    logger.info("Stripe⇔DB整合性チェック開始")
    
    stripe.api_key = get_stripe_secret_key()
    
    db = SessionLocal()
    inconsistencies = []
    
    try:
        # 1. DBのアクティブな購読を取得
        db_subscriptions = db.query(Subscription).filter(
            Subscription.stripe_subscription_id != None,
            Subscription.status.in_(["trialing", "active", "past_due"]),
        ).all()
        
        db_sub_map = {sub.stripe_subscription_id: sub for sub in db_subscriptions}
        logger.info(f"DB上のアクティブ購読数: {len(db_subscriptions)}")
        
        # 2. Stripeのアクティブな購読を取得
        stripe_subscriptions = []
        has_more = True
        starting_after = None
        
        while has_more:
            params = {
                "status": "all",  # trialing, active, past_due, canceled等全て
                "limit": 100,
            }
            if starting_after:
                params["starting_after"] = starting_after
            
            result = stripe.Subscription.list(**params)
            stripe_subscriptions.extend(result.data)
            has_more = result.has_more
            if result.data:
                starting_after = result.data[-1].id
        
        logger.info(f"Stripe上の購読数: {len(stripe_subscriptions)}")
        
        # 3. 比較
        checked_stripe_ids = set()
        
        for stripe_sub in stripe_subscriptions:
            stripe_id = stripe_sub.id
            stripe_status = stripe_sub.status
            checked_stripe_ids.add(stripe_id)
            
            # Stripeでアクティブな購読がDBにない
            if stripe_status in ["trialing", "active", "past_due"]:
                if stripe_id not in db_sub_map:
                    # DBにレコードがあるか確認（キャンセル済み等）
                    existing = db.query(Subscription).filter(
                        Subscription.stripe_subscription_id == stripe_id
                    ).first()
                    if not existing:
                        inconsistencies.append({
                            "type": "MISSING_IN_DB",
                            "stripe_subscription_id": stripe_id,
                            "stripe_status": stripe_status,
                            "customer_id": stripe_sub.customer,
                            "message": f"Stripeにアクティブな購読があるがDBに存在しない",
                        })
                    elif existing.status != stripe_status:
                        inconsistencies.append({
                            "type": "STATUS_MISMATCH",
                            "stripe_subscription_id": stripe_id,
                            "stripe_status": stripe_status,
                            "db_status": existing.status,
                            "message": f"ステータス不一致: Stripe={stripe_status}, DB={existing.status}",
                        })
                else:
                    db_sub = db_sub_map[stripe_id]
                    # ステータス比較
                    if db_sub.status != stripe_status:
                        inconsistencies.append({
                            "type": "STATUS_MISMATCH",
                            "stripe_subscription_id": stripe_id,
                            "stripe_status": stripe_status,
                            "db_status": db_sub.status,
                            "subscription_id": db_sub.id,
                            "message": f"ステータス不一致: Stripe={stripe_status}, DB={db_sub.status}",
                        })
                    
                    # cancel_at_period_end比較
                    if db_sub.cancel_at_period_end != stripe_sub.cancel_at_period_end:
                        inconsistencies.append({
                            "type": "CANCEL_FLAG_MISMATCH",
                            "stripe_subscription_id": stripe_id,
                            "stripe_cancel_at_period_end": stripe_sub.cancel_at_period_end,
                            "db_cancel_at_period_end": db_sub.cancel_at_period_end,
                            "subscription_id": db_sub.id,
                            "message": f"キャンセル予約フラグ不一致: Stripe={stripe_sub.cancel_at_period_end}, DB={db_sub.cancel_at_period_end}",
                        })
            
            # Stripeでキャンセル済みなのにDBでアクティブ
            elif stripe_status == "canceled":
                if stripe_id in db_sub_map:
                    db_sub = db_sub_map[stripe_id]
                    inconsistencies.append({
                        "type": "CANCELED_BUT_ACTIVE_IN_DB",
                        "stripe_subscription_id": stripe_id,
                        "stripe_status": stripe_status,
                        "db_status": db_sub.status,
                        "subscription_id": db_sub.id,
                        "message": f"Stripeでキャンセル済みだがDBでアクティブ",
                    })
        
        # 4. DBにあるがStripeにない購読（削除された等）
        for stripe_id, db_sub in db_sub_map.items():
            if stripe_id not in checked_stripe_ids:
                # Stripeから取得できなかった購読
                try:
                    stripe_sub = stripe.Subscription.retrieve(stripe_id)
                    if stripe_sub.status == "canceled" and db_sub.status != "canceled":
                        inconsistencies.append({
                            "type": "CANCELED_BUT_ACTIVE_IN_DB",
                            "stripe_subscription_id": stripe_id,
                            "stripe_status": stripe_sub.status,
                            "db_status": db_sub.status,
                            "subscription_id": db_sub.id,
                            "message": f"Stripeでキャンセル済みだがDBでアクティブ",
                        })
                except stripe.error.InvalidRequestError:
                    inconsistencies.append({
                        "type": "NOT_FOUND_IN_STRIPE",
                        "stripe_subscription_id": stripe_id,
                        "db_status": db_sub.status,
                        "subscription_id": db_sub.id,
                        "message": f"Stripeに購読が存在しない",
                    })
        
        # 5. 結果をログ出力
        if inconsistencies:
            logger.warning(f"整合性チェック完了: {len(inconsistencies)}件の不一致を検出")
            for item in inconsistencies:
                logger.warning(f"不一致: {item}")
            
            # 管理者にメール通知
            _send_inconsistency_alert(db, inconsistencies)
        else:
            logger.info("整合性チェック完了: 不一致なし")
        
        return inconsistencies
        
    except Exception as e:
        logger.error(f"整合性チェックエラー: {e}")
        raise
    finally:
        db.close()


def _send_inconsistency_alert(db: Session, inconsistencies: list):
    """不一致が検出された場合に管理者に通知"""
    from app.services.mail_service import send_admin_alert_email
    
    now = datetime.now(JST)
    
    # 不一致の種類ごとにカウント
    type_counts = {}
    for item in inconsistencies:
        t = item.get("type", "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1
    
    # 詳細テキスト作成
    details_lines = []
    for item in inconsistencies[:10]:  # 最大10件まで詳細表示
        details_lines.append(
            f"- [{item.get('type')}] {item.get('stripe_subscription_id')}: {item.get('message')}"
        )
    
    if len(inconsistencies) > 10:
        details_lines.append(f"... 他 {len(inconsistencies) - 10} 件")
    
    details = "\n".join(details_lines)
    type_summary = ", ".join([f"{k}: {v}件" for k, v in type_counts.items()])
    
    subject = f"【警告】Stripe⇔DB整合性チェック: {len(inconsistencies)}件の不一致"
    body = f"""Stripe⇔DB整合性チェックで不一致が検出されました。

実行日時: {now.strftime('%Y-%m-%d %H:%M:%S')} JST
検出件数: {len(inconsistencies)}件
種類別: {type_summary}

【詳細】
{details}

---
このメールはシステムから自動送信されています。
管理画面で購読状態を確認し、必要に応じて手動で修正してください。
"""
    
    try:
        send_admin_alert_email(subject, body)
        logger.info("整合性チェックアラートメール送信完了")
    except Exception as e:
        logger.error(f"整合性チェックアラートメール送信失敗: {e}")
