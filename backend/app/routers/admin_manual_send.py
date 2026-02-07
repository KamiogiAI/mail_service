"""管理画面: 手動送信 (入力内容をそのまま送信)"""
import time as _time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import get_db
from app.core.config import settings
from app.models.plan import Plan
from app.models.user import User
from app.models.subscription import Subscription
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.services.resend_service import send_email
from app.routers.deps import require_admin
from app.core.logging import get_logger

router = APIRouter(prefix="/api/admin/manual-send", tags=["admin-manual-send"])
logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")

THROTTLE_SECONDS = 5


class ManualSendUserRequest(BaseModel):
    user_id: int
    subject: str
    body: str


class ManualSendPlanRequest(BaseModel):
    plan_id: int
    subject: str
    body: str


@router.post("/user")
async def manual_send_user(
    req: ManualSendUserRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """個別手動送信 (ユーザーID指定)"""
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    if not req.subject.strip() or not req.body.strip():
        raise HTTPException(status_code=400, detail="件名と本文は必須です")

    # Delivery レコード
    delivery = Delivery(
        plan_id=None,
        send_type="manual",
        status="running",
        subject=req.subject,
        total_count=1,
        started_at=datetime.now(JST),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)

    # 配信停止URL
    unsubscribe_url = None
    if user.unsubscribe_token:
        unsubscribe_url = f"{settings.SITE_URL}/api/me/unsubscribe?token={user.unsubscribe_token}"

    try:
        result = send_email(
            to_email=user.email,
            subject=req.subject,
            body=req.body,
            unsubscribe_url=unsubscribe_url,
        )
        item = DeliveryItem(
            delivery_id=delivery.id,
            user_id=user.id,
            member_no_snapshot=user.member_no,
            status=2,
            resend_message_id=result.get("id"),
            sent_at=datetime.now(JST),
        )
        db.add(item)
        delivery.success_count = 1
        delivery.fail_count = 0
        delivery.status = "success"
    except Exception as e:
        item = DeliveryItem(
            delivery_id=delivery.id,
            user_id=user.id,
            member_no_snapshot=user.member_no,
            status=3,
            last_error_message=str(e),
        )
        db.add(item)
        delivery.success_count = 0
        delivery.fail_count = 1
        delivery.status = "failed"
        logger.error(f"手動送信失敗: user_id={user.id} - {e}")

    delivery.completed_at = datetime.now(JST)
    db.commit()

    return {
        "message": "送信完了" if delivery.status == "success" else "送信失敗",
        "delivery_id": delivery.id,
        "status": delivery.status,
    }


@router.post("/plan")
async def manual_send_plan(
    req: ManualSendPlanRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """全員手動送信 (プラン加入者全員)"""
    plan = db.query(Plan).filter(Plan.id == req.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="プランが見つかりません")

    if not req.subject.strip() or not req.body.strip():
        raise HTTPException(status_code=400, detail="件名と本文は必須です")

    # 対象ユーザー取得
    users = db.query(User).join(
        Subscription, Subscription.user_id == User.id
    ).filter(
        Subscription.plan_id == plan.id,
        Subscription.status.in_(["trialing", "active", "admin_added"]),
        User.is_active == True,
        User.deliverable == True,
        User.email_verified == True,
    ).all()

    if not users:
        raise HTTPException(status_code=400, detail="配信対象ユーザーがいません")

    # Delivery レコード
    delivery = Delivery(
        plan_id=plan.id,
        send_type="manual",
        status="running",
        subject=req.subject,
        total_count=len(users),
        started_at=datetime.now(JST),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)

    success_count = 0
    fail_count = 0

    for user in users:
        unsubscribe_url = None
        if user.unsubscribe_token:
            unsubscribe_url = f"{settings.SITE_URL}/api/me/unsubscribe?token={user.unsubscribe_token}"

        try:
            result = send_email(
                to_email=user.email,
                subject=req.subject,
                body=req.body,
                unsubscribe_url=unsubscribe_url,
            )
            item = DeliveryItem(
                delivery_id=delivery.id,
                user_id=user.id,
                member_no_snapshot=user.member_no,
                status=2,
                resend_message_id=result.get("id"),
                sent_at=datetime.now(JST),
            )
            db.add(item)
            success_count += 1
        except Exception as e:
            item = DeliveryItem(
                delivery_id=delivery.id,
                user_id=user.id,
                member_no_snapshot=user.member_no,
                status=3,
                last_error_message=str(e),
            )
            db.add(item)
            fail_count += 1
            logger.error(f"手動送信失敗: user_id={user.id} - {e}")

        db.commit()
        _time.sleep(THROTTLE_SECONDS)

    # 完了更新
    delivery.success_count = success_count
    delivery.fail_count = fail_count
    delivery.completed_at = datetime.now(JST)
    if fail_count == 0:
        delivery.status = "success"
    elif success_count == 0:
        delivery.status = "failed"
    else:
        delivery.status = "partial_failed"
    db.commit()

    return {
        "message": "全員送信完了",
        "delivery_id": delivery.id,
        "status": delivery.status,
        "success_count": success_count,
        "fail_count": fail_count,
    }
