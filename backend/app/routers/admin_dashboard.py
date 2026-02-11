"""管理画面: ダッシュボード統計"""
from datetime import datetime, time
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.core.database import get_db
from app.models.user import User
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.models.system_log import SystemLog
from app.routers.deps import require_admin

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])
JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")
ACTIVE_STATUSES = ("trialing", "active", "past_due", "admin_added")


def _to_jst_iso(dt: datetime) -> str:
    """DateTimeをJSTに変換してISO形式で返す"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(JST).isoformat()


@router.get("")
async def get_dashboard(db: Session = Depends(get_db), _=Depends(require_admin)):
    """ダッシュボード統計データ"""
    now = datetime.now(JST)
    today_start = datetime.combine(now.date(), time.min).replace(tzinfo=JST)

    # --- ユーザー統計 ---
    total_users = db.query(sa_func.count(User.id)).filter(User.role == "user").scalar()
    active_users = db.query(sa_func.count(User.id)).filter(
        User.role == "user", User.is_active == True, User.email_verified == True,
    ).scalar()

    # --- 購読統計 ---
    subs = (
        db.query(Subscription.status, sa_func.count(Subscription.id))
        .filter(Subscription.status.in_(ACTIVE_STATUSES))
        .group_by(Subscription.status)
        .all()
    )
    sub_counts = {s: c for s, c in subs}
    total_active_subs = sum(sub_counts.values())
    trialing_subs = sub_counts.get("trialing", 0)

    # --- 月額売上 (admin_added は支払いなしなので除外) ---
    PAID_STATUSES = ("trialing", "active", "past_due")
    revenue_rows = (
        db.query(Plan.price, sa_func.count(Subscription.id))
        .join(Subscription, Subscription.plan_id == Plan.id)
        .filter(Subscription.status.in_(PAID_STATUSES))
        .group_by(Plan.id)
        .all()
    )
    monthly_revenue = sum(price * cnt for price, cnt in revenue_rows)

    # --- プラン別加入者数 ---
    plan_breakdown = (
        db.query(Plan.name, Plan.price, sa_func.count(Subscription.id))
        .join(Subscription, Subscription.plan_id == Plan.id)
        .filter(Subscription.status.in_(ACTIVE_STATUSES))
        .group_by(Plan.id)
        .order_by(sa_func.count(Subscription.id).desc())
        .all()
    )
    plans_summary = [
        {"name": name, "price": price, "count": cnt}
        for name, price, cnt in plan_breakdown
    ]

    # --- 本日の配信統計 ---
    today_deliveries = db.query(Delivery).filter(
        Delivery.created_at >= today_start,
    ).all()
    today_sent = sum(d.total_count for d in today_deliveries)
    today_success = sum(d.success_count for d in today_deliveries)
    today_fail = sum(d.fail_count for d in today_deliveries)
    today_delivery_count = len(today_deliveries)

    # --- 本日のエラー/警告 ---
    today_errors = db.query(sa_func.count(SystemLog.id)).filter(
        SystemLog.created_at >= today_start,
        SystemLog.level.in_(["ERROR", "CRITICAL"]),
    ).scalar()
    today_warnings = db.query(sa_func.count(SystemLog.id)).filter(
        SystemLog.created_at >= today_start,
        SystemLog.level == "WARNING",
    ).scalar()

    # --- 最近の配信 (5件) ---
    recent_deliveries = (
        db.query(Delivery, Plan.name)
        .join(Plan, Delivery.plan_id == Plan.id, isouter=True)
        .order_by(Delivery.created_at.desc())
        .limit(5)
        .all()
    )
    recent_deliveries_list = [
        {
            "id": d.id,
            "plan_name": pname or "(なし)",
            "send_type": d.send_type,
            "subject": d.subject,
            "total": d.total_count,
            "success": d.success_count,
            "fail": d.fail_count,
            "status": d.status,
            "created_at": _to_jst_iso(d.created_at),
        }
        for d, pname in recent_deliveries
    ]

    # --- 最近の新規登録 (5件) ---
    recent_users = (
        db.query(User)
        .filter(User.role == "user")
        .order_by(User.created_at.desc())
        .limit(5)
        .all()
    )
    recent_users_list = [
        {
            "id": u.id,
            "member_no": u.member_no,
            "name": f"{u.name_last} {u.name_first}",
            "email": u.email,
            "created_at": _to_jst_iso(u.created_at),
        }
        for u in recent_users
    ]

    return {
        "users": {
            "total": total_users,
            "active": active_users,
        },
        "subscriptions": {
            "total_active": total_active_subs,
            "trialing": trialing_subs,
        },
        "revenue": {
            "monthly": monthly_revenue,
        },
        "plans_summary": plans_summary,
        "today": {
            "delivery_count": today_delivery_count,
            "sent": today_sent,
            "success": today_success,
            "fail": today_fail,
            "errors": today_errors,
            "warnings": today_warnings,
        },
        "recent_deliveries": recent_deliveries_list,
        "recent_users": recent_users_list,
    }
