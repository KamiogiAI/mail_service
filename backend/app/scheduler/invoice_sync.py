"""Stripe Invoice 同期バッチ（日次整合性チェック）"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.database import SessionLocal
from app.core.api_keys import get_stripe_secret_key
from app.models.invoice_record import InvoiceRecord
from app.models.subscription import Subscription
from app.models.user import User
from app.models.promotion_code import PromotionCode
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def sync_invoices_from_stripe():
    """Stripeから過去30日のInvoiceを取得して同期（取りこぼし対策）"""
    import stripe
    stripe.api_key = get_stripe_secret_key()
    
    db = SessionLocal()
    try:
        # 過去30日のInvoiceを取得
        thirty_days_ago = datetime.now(JST) - timedelta(days=30)
        created_after = int(thirty_days_ago.timestamp())
        
        invoices = stripe.Invoice.list(
            created={"gte": created_after},
            status="paid",
            limit=100,
        )
        
        synced_count = 0
        skipped_count = 0
        
        for inv in invoices.auto_paging_iter():
            try:
                stripe_invoice_id = inv.id
                
                # 既存チェック
                existing = db.query(InvoiceRecord).filter(
                    InvoiceRecord.stripe_invoice_id == stripe_invoice_id
                ).first()
                if existing:
                    skipped_count += 1
                    continue
                
                # ユーザーと購読を取得
                customer_id = inv.customer
                stripe_subscription_id = inv.subscription
                
                user = db.query(User).filter(
                    User.stripe_customer_id == customer_id
                ).first() if customer_id else None
                
                sub = db.query(Subscription).filter(
                    Subscription.stripe_subscription_id == stripe_subscription_id
                ).first() if stripe_subscription_id else None
                
                # 割引情報
                discount = inv.discount or {}
                coupon = discount.coupon if hasattr(discount, 'coupon') else None
                coupon_id = coupon.id if coupon else None
                
                # プロモコード検索
                promo = None
                if coupon_id:
                    promo = db.query(PromotionCode).filter(
                        PromotionCode.stripe_coupon_id == coupon_id
                    ).first()
                
                # 割引額
                discount_amount = 0
                if inv.total_discount_amounts:
                    discount_amount = sum(d.amount for d in inv.total_discount_amounts)
                
                # 期間
                period_start = None
                period_end = None
                if inv.lines and inv.lines.data:
                    line = inv.lines.data[0]
                    if line.period:
                        period_start = datetime.fromtimestamp(line.period.start) if line.period.start else None
                        period_end = datetime.fromtimestamp(line.period.end) if line.period.end else None
                
                record = InvoiceRecord(
                    stripe_invoice_id=stripe_invoice_id,
                    stripe_subscription_id=stripe_subscription_id,
                    subscription_id=sub.id if sub else None,
                    user_id=user.id if user else None,
                    amount_paid=inv.amount_paid or 0,
                    subtotal=inv.subtotal or 0,
                    discount_amount=discount_amount,
                    promotion_code_id=promo.id if promo else None,
                    coupon_id=coupon_id,
                    period_start=period_start,
                    period_end=period_end,
                    status="paid",
                )
                db.add(record)
                db.commit()  # 1件ずつコミット（1件失敗しても他は保存される）
                synced_count += 1
            except Exception as e:
                logger.warning(f"Invoice個別同期エラー: invoice={inv.id}, error={e}")
                db.rollback()
                continue
        logger.info(f"Invoice同期完了: synced={synced_count}, skipped={skipped_count}")
        
    except Exception as e:
        logger.error(f"Invoice同期エラー: {e}")
        db.rollback()
    finally:
        db.close()
