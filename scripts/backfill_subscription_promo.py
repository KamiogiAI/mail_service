#!/usr/bin/env python3
"""既存のサブスクリプションにプロモーションコードを紐付けるスクリプト

使用方法:
    cd /opt/mail_service
    docker compose exec api python /app/scripts/backfill_subscription_promo.py
"""
import sys
sys.path.insert(0, "/app")

from app.core.database import SessionLocal
from app.core.api_keys import get_stripe_secret_key
from app.models.subscription import Subscription
from app.models.promotion_code import PromotionCode

import stripe
stripe.api_key = get_stripe_secret_key()


def main():
    db = SessionLocal()
    try:
        # プロモーションコードが未設定のサブスクリプションを取得
        subs = db.query(Subscription).filter(
            Subscription.promotion_code_id == None,
            Subscription.stripe_subscription_id != None,
        ).all()
        
        print(f"対象サブスクリプション: {len(subs)}件")
        
        updated = 0
        for sub in subs:
            try:
                # Stripeからサブスクリプション情報を取得
                stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
                
                if not stripe_sub.discount:
                    continue
                
                coupon = stripe_sub.discount.coupon
                if not coupon:
                    continue
                
                stripe_coupon_id = coupon.id
                
                # DBでPromotionCodeを検索
                promo = db.query(PromotionCode).filter(
                    PromotionCode.stripe_coupon_id == stripe_coupon_id
                ).first()
                
                if promo:
                    sub.promotion_code_id = promo.id
                    print(f"  subscription_id={sub.id}: promo={promo.code}")
                    updated += 1
                else:
                    print(f"  subscription_id={sub.id}: unknown coupon={stripe_coupon_id}")
                    
            except Exception as e:
                print(f"  subscription_id={sub.id}: error={e}")
                continue
        
        if updated > 0:
            db.commit()
            print(f"\n更新完了: {updated}件")
        else:
            print("\n更新対象なし")
            
    finally:
        db.close()


if __name__ == "__main__":
    main()
