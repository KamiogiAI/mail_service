"""管理画面: システムログ"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.database import get_db
from app.models.system_log import SystemLog
from app.routers.deps import require_admin

router = APIRouter(prefix="/api/admin/logs", tags=["admin-logs"])


@router.get("")
async def list_logs(
    level: Optional[str] = None,
    event_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """ログ一覧"""
    q = db.query(SystemLog)
    if level:
        q = q.filter(SystemLog.level == level)
    if event_type:
        q = q.filter(SystemLog.event_type == event_type)
    if start_date:
        q = q.filter(SystemLog.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        q = q.filter(SystemLog.created_at <= datetime.combine(end_date, datetime.max.time()))

    total = q.count()
    logs = q.order_by(SystemLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "logs": [
            {
                "id": l.id,
                "level": l.level,
                "event_type": l.event_type,
                "plan_id": l.plan_id,
                "user_id": l.user_id,
                "member_no_snapshot": l.member_no_snapshot,
                "delivery_id": l.delivery_id,
                "message": l.message,
                "details": l.details,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@router.delete("/bulk-delete")
async def bulk_delete_logs(
    before_date: date,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """指定日付以前のログを一括削除"""
    threshold = datetime.combine(before_date, datetime.max.time())
    count = db.query(SystemLog).filter(SystemLog.created_at <= threshold).delete()
    db.commit()
    return {"message": f"{count}件のログを削除しました"}
