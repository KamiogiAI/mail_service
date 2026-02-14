"""管理画面: ユーザー管理"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.models.user import User
from app.models.subscription import Subscription
from app.models.plan import Plan
from app.services import auth_service, stripe_service
from app.services.mail_service import send_verify_code_email
from app.routers.deps import require_admin

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])

ACTIVE_STATUSES = ("trialing", "active", "past_due", "admin_added")


class UpdateUserRole(BaseModel):
    role: str  # "user" or "admin"


class UpdateUserSubscriptions(BaseModel):
    plan_ids: list[int]


class InviteAdminRequest(BaseModel):
    email: EmailStr
    name_last: str
    name_first: str


@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """ユーザー一覧"""
    q = db.query(User)
    if search:
        q = q.filter(
            (User.email.contains(search))
            | (User.member_no.contains(search))
            | (User.name_last.contains(search))
            | (User.name_first.contains(search))
        )
    if role:
        q = q.filter(User.role == role)

    total = q.count()
    users = q.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    # 各ユーザーの加入プランを一括取得
    user_ids = [u.id for u in users]
    subs = (
        db.query(Subscription.user_id, Plan.id, Plan.name)
        .join(Plan, Subscription.plan_id == Plan.id)
        .filter(
            Subscription.user_id.in_(user_ids),
            Subscription.status.in_(ACTIVE_STATUSES),
        )
        .all()
    ) if user_ids else []

    # user_id → [{plan_id, plan_name}] のマップ
    plan_map: dict[int, list] = {}
    for uid, pid, pname in subs:
        plan_map.setdefault(uid, []).append({"plan_id": pid, "plan_name": pname})

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "users": [
            {
                "id": u.id,
                "member_no": u.member_no,
                "email": u.email,
                "name_last": u.name_last,
                "name_first": u.name_first,
                "role": u.role,
                "is_active": u.is_active,
                "email_verified": u.email_verified,
                "deliverable": u.deliverable,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "plans": plan_map.get(u.id, []),
            }
            for u in users
        ],
    }


@router.get("/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """ユーザー詳細"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    subs = db.query(Subscription).filter(Subscription.user_id == user_id).all()

    return {
        "id": user.id,
        "member_no": user.member_no,
        "email": user.email,
        "name_last": user.name_last,
        "name_first": user.name_first,
        "role": user.role,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "deliverable": user.deliverable,
        "trial_used": user.trial_used,
        "stripe_customer_id": user.stripe_customer_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "subscriptions": [
            {
                "id": s.id,
                "plan_id": s.plan_id,
                "status": s.status,
                "cancel_at_period_end": s.cancel_at_period_end,
                "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None,
            }
            for s in subs
        ],
    }


@router.put("/{user_id}/role")
async def update_role(
    user_id: int,
    data: UpdateUserRole,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """ロール変更"""
    if data.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="無効なロールです")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    user.role = data.role
    db.commit()
    return {"message": f"ロールを{data.role}に変更しました"}


@router.put("/{user_id}/toggle-active")
async def toggle_active(user_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """有効/無効切替"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    # 管理者アカウントの無効化を禁止
    if user.role == "admin" and user.is_active:
        raise HTTPException(status_code=400, detail="管理者アカウントは無効化できません")

    # 無効化する場合、Stripeサブスクリプションをキャンセル
    if user.is_active:
        subs = db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.status.in_(("trialing", "active", "past_due")),
            Subscription.stripe_subscription_id != None,
        ).all()
        for sub in subs:
            try:
                stripe_service.cancel_subscription(sub.stripe_subscription_id, at_period_end=True)
                sub.cancel_at_period_end = True
            except Exception:
                pass  # Stripe側で既にキャンセル済みの場合など

    user.is_active = not user.is_active
    db.commit()
    return {"message": f"ユーザーを{'有効' if user.is_active else '無効'}にしました", "is_active": user.is_active}


@router.put("/{user_id}/subscriptions")
async def update_user_subscriptions(
    user_id: int,
    data: UpdateUserSubscriptions,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """管理者によるユーザー購読変更 (チェックボックス式)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    # 現在のアクティブ購読
    current_subs = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.status.in_(ACTIVE_STATUSES),
    ).all()
    current_plan_ids = {s.plan_id for s in current_subs}
    new_plan_ids = set(data.plan_ids)

    # 解除: チェックを外されたプラン
    for sub in current_subs:
        if sub.plan_id not in new_plan_ids:
            if sub.stripe_subscription_id:
                try:
                    stripe_service.cancel_subscription_immediately(sub.stripe_subscription_id)
                except Exception:
                    pass
            sub.status = "canceled"

    # 追加: 新たにチェックされたプラン
    for pid in new_plan_ids - current_plan_ids:
        plan = db.query(Plan).filter(Plan.id == pid, Plan.is_active == True).first()
        if not plan:
            continue
        sub = Subscription(
            user_id=user_id,
            plan_id=pid,
            member_no_snapshot=user.member_no,
            status="admin_added",
        )
        db.add(sub)

    db.commit()
    return {"message": "購読を更新しました"}


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    """ユーザー削除 (Stripe購読解約 → user_id NULL化 → 物理削除)"""
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="自分自身は削除できません")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    if user.role == "admin":
        raise HTTPException(status_code=400, detail="管理者アカウントは削除できません。先にロールを変更してください")

    # Stripe購読解約
    subs = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.status.in_(["trialing", "active", "admin_added"]),
    ).all()
    for sub in subs:
        if sub.stripe_subscription_id:
            try:
                stripe_service.cancel_subscription_immediately(sub.stripe_subscription_id)
            except Exception:
                pass
        sub.status = "canceled"
        sub.user_id = None

    # 関連テーブルのuser_id NULL化 (delivery_items, system_logs等)
    from app.models.delivery_item import DeliveryItem
    from app.models.system_log import SystemLog
    from app.models.progress_task import ProgressTask
    db.query(DeliveryItem).filter(DeliveryItem.user_id == user_id).update({"user_id": None})
    db.query(SystemLog).filter(SystemLog.user_id == user_id).update({"user_id": None})
    db.query(ProgressTask).filter(ProgressTask.user_id == user_id).update({"user_id": None})

    # 物理削除
    db.delete(user)
    db.commit()
    return {"message": "ユーザーを削除しました"}


@router.post("/invite-admin")
async def invite_admin(
    data: InviteAdminRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """管理者招待 (仮パスワードで作成 → メールで通知)"""
    from app.services.mail_service import send_admin_invite_email
    
    existing = auth_service.get_user_by_email(db, data.email)
    if existing:
        if existing.role == "admin":
            raise HTTPException(status_code=400, detail="既に管理者として登録されています")
        # 一般会員を管理者に昇格
        existing.role = "admin"
        db.commit()
        return {"message": f"{data.email} を管理者に昇格しました"}

    # 仮パスワードで新規作成
    import secrets
    temp_password = secrets.token_urlsafe(16)
    user = auth_service.create_user(
        db=db,
        email=data.email,
        password=temp_password,
        name_last=data.name_last,
        name_first=data.name_first,
        role="admin",
    )
    
    # 仮パスワードをメールで送信（APIレスポンスには含めない）
    name = f"{data.name_last} {data.name_first}"
    if not send_admin_invite_email(data.email, name, temp_password):
        # メール送信失敗時はユーザーを削除してエラー
        db.delete(user)
        db.commit()
        raise HTTPException(status_code=500, detail="招待メールの送信に失敗しました")

    return {"message": f"管理者を招待しました。仮パスワードをメールで送信しました: {data.email}"}
