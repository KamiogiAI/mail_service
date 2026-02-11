"""管理画面: 配信履歴"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.database import get_db

JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")


def _to_jst_iso(dt: datetime) -> str:
    """DateTimeをJSTに変換してISO形式で返す (UTC保存のカラム用)"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(JST).isoformat()


def _jst_iso(dt: datetime) -> str:
    """既にJSTで保存されているDateTimeをISO形式で返す (started_at/completed_at用)"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.isoformat()
from app.models.delivery import Delivery
from app.models.plan import Plan
from app.routers.deps import require_admin

router = APIRouter(prefix="/api/admin/deliveries", tags=["admin-deliveries"])


@router.get("")
async def list_deliveries(
    send_type: Optional[str] = None,
    target_date: Optional[date] = Query(None, alias="date"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    limit: Optional[int] = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """配信履歴一覧"""
    q = db.query(Delivery)
    if send_type:
        q = q.filter(Delivery.send_type == send_type)
    if target_date:
        q = q.filter(
            Delivery.created_at >= datetime.combine(target_date, datetime.min.time()),
            Delivery.created_at <= datetime.combine(target_date, datetime.max.time()),
        )

    total = q.count()
    if limit:
        deliveries = q.order_by(Delivery.created_at.desc()).limit(limit).all()
    else:
        deliveries = q.order_by(Delivery.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    result = []
    for d in deliveries:
        plan = db.query(Plan).filter(Plan.id == d.plan_id).first()
        result.append({
            "id": d.id,
            "plan_id": d.plan_id,
            "plan_name": plan.name if plan else "(削除済)",
            "send_type": d.send_type,
            "status": d.status,
            "subject": d.subject,
            "total_count": d.total_count,
            "success_count": d.success_count,
            "fail_count": d.fail_count,
            "started_at": _jst_iso(d.started_at),
            "completed_at": _jst_iso(d.completed_at),
            "created_at": _to_jst_iso(d.created_at),
        })

    return {"total": total, "deliveries": result}


@router.delete("/{delivery_id}")
async def delete_delivery(delivery_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """配信履歴削除"""
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="配信履歴が見つかりません")
    db.delete(delivery)
    db.commit()
    return {"message": "削除しました"}


@router.post("/{delivery_id}/retry-failed")
async def retry_failed_items(delivery_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """失敗したユーザーにのみ再送"""
    from app.services.delivery_service import retry_failed_delivery
    from app.models.delivery_item import DeliveryItem

    # 失敗件数を先に確認
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="配信履歴が見つかりません")

    failed_count = db.query(DeliveryItem).filter(
        DeliveryItem.delivery_id == delivery_id,
        DeliveryItem.status == 3,
    ).count()

    if failed_count == 0:
        return {"message": "再送対象の失敗ユーザーがいません", "retried": 0, "success": 0, "failed": 0}

    result = retry_failed_delivery(db, delivery_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
