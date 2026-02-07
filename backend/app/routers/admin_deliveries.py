"""管理画面: 配信履歴"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime

from app.core.database import get_db
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
            "started_at": d.started_at.isoformat() if d.started_at else None,
            "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
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
