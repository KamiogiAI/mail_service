"""トライアル終了間近リマインダー (3日前にメール送信)"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.subscription import Subscription
from app.models.plan import Plan
from app.models.user import User
from app.services.mail_service import send_trial_ending_email
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def check_trial_ending():
    """トライアル終了3日前のユーザーにリマインダーメールを送信"""
    db = SessionLocal()
    try:
        now = datetime.now(JST)
        # 3日後の日付範囲（その日の00:00〜23:59）
        target_date = (now + timedelta(days=3)).date()
        target_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=JST)
        target_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=JST)
        
        # トライアル中で、3日後に終了するサブスクリプションを取得
        subs = db.query(Subscription).filter(
            Subscription.status == "trialing",
            Subscription.trial_end >= target_start,
            Subscription.trial_end <= target_end,
        ).all()
        
        if not subs:
            logger.info("トライアル終了間近のユーザーなし")
            return
        
        sent_count = 0
        for sub in subs:
            user = db.query(User).filter(User.id == sub.user_id).first()
            plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
            
            if not user or not plan:
                continue
            
            if not user.is_active:
                continue
            
            trial_end_str = sub.trial_end.astimezone(JST).strftime("%Y年%m月%d日") if sub.trial_end else "-"
            
            if send_trial_ending_email(
                to_email=user.email,
                name=f"{user.name_last} {user.name_first}",
                plan_name=plan.name,
                plan_price=plan.price,
                trial_end_date=trial_end_str,
            ):
                sent_count += 1
        
        logger.info(f"トライアル終了間近リマインダー送信: {sent_count}件")
    
    except Exception as e:
        logger.error(f"トライアル終了間近チェックエラー: {e}")
    finally:
        db.close()
