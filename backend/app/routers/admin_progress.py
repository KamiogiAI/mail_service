"""管理画面: 進捗モニタリング・リセット・緊急停止"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.progress_plan import ProgressPlan
from app.models.plan import Plan
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.models.user import User
from app.worker.throttle_manager import set_emergency_stop, check_emergency_stop
from app.routers.deps import require_admin

router = APIRouter(prefix="/api/admin/progress", tags=["admin-progress"])

STATUS_LABELS = {0: "未実行", 1: "実行中", 2: "完了", 3: "エラー"}
JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")


def _to_jst_iso(dt: datetime) -> str:
    """DateTimeをJSTに変換してISO形式で返す (UTC保存のカラム用)"""
    if dt is None:
        return None
    # タイムゾーンなしの場合はUTCとして扱う
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(JST).isoformat()


def _jst_iso(dt: datetime) -> str:
    """既にJSTで保存されているDateTimeをISO形式で返す (started_at/completed_at用)"""
    if dt is None:
        return None
    # 既にJSTで保存されているのでそのまま出力
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.isoformat()


def _today_jst():
    return datetime.now(ZoneInfo("Asia/Tokyo")).date()


@router.get("/scheduler-status")
async def get_scheduler_status(db: Session = Depends(get_db), _=Depends(require_admin)):
    """スケジューラー状態チェック"""
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    today = now.date()
    weekday = now.weekday()  # 0=月〜6=日
    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    schedule_type_label = {"daily": "毎日", "weekday": "曜日指定", "sheets": "シート連動"}

    # ハートビート確認
    redis = await get_redis()
    heartbeat = await redis.get("scheduler:heartbeat")
    scheduler_alive = False
    last_heartbeat = None
    if heartbeat:
        last_heartbeat = heartbeat
        try:
            hb_time = datetime.fromisoformat(heartbeat)
            diff = (now - hb_time).total_seconds()
            scheduler_alive = diff < 180
        except (ValueError, TypeError):
            pass

    # 緊急停止
    emergency_stop = check_emergency_stop()

    # 全有効プランの状態
    plans = db.query(Plan).filter(Plan.is_active == True).order_by(Plan.sort_order.asc()).all()
    today_items = db.query(ProgressPlan).filter(ProgressPlan.date == today).all()

    plan_statuses = []
    for pl in plans:
        # 本日実行対象か判定
        is_today_target = False
        target_reason = ""
        if pl.schedule_type == "daily":
            is_today_target = True
            target_reason = "毎日実行"
        elif pl.schedule_type == "weekday":
            if pl.schedule_weekdays and weekday in [int(d) for d in pl.schedule_weekdays if _safe_int(d) is not None]:
                is_today_target = True
                target_reason = f"{weekday_names[weekday]}曜日が対象"
            else:
                configured = ""
                if pl.schedule_weekdays:
                    try:
                        configured = ", ".join(weekday_names[int(d)] for d in pl.schedule_weekdays if int(d) < 7)
                    except (ValueError, TypeError, IndexError):
                        pass
                target_reason = f"対象曜日: {configured or '未設定'} (今日は{weekday_names[weekday]})"
        elif pl.schedule_type == "sheets":
            target_reason = "シート連動 (実行時に判定)"
        else:
            target_reason = "スケジュール未設定"

        # 今日の進捗
        today_pp = next((tp for tp in today_items if tp.plan_id == pl.id), None)
        today_status = None
        today_status_label = "未実行"
        if today_pp:
            today_status = today_pp.status
            today_status_label = STATUS_LABELS.get(today_pp.status, "不明")

        # 配信済みか
        sent_today = False
        delivery_info = None
        if today_pp and today_pp.delivery_id:
            delivery = db.query(Delivery).filter(Delivery.id == today_pp.delivery_id).first()
            if delivery:
                sent_today = delivery.status in ("success", "partial_failed")
                delivery_info = {
                    "status": delivery.status,
                    "total_count": delivery.total_count,
                    "success_count": delivery.success_count,
                    "fail_count": delivery.fail_count,
                }

        plan_statuses.append({
            "plan_id": pl.id,
            "plan_name": pl.name,
            "schedule_type": schedule_type_label.get(pl.schedule_type, pl.schedule_type or "-"),
            "send_time": pl.send_time.strftime("%H:%M") if pl.send_time else "-",
            "is_today_target": is_today_target,
            "target_reason": target_reason,
            "today_status": today_status,
            "today_status_label": today_status_label,
            "sent_today": sent_today,
            "delivery_info": delivery_info,
        })

    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_weekday": f"{weekday_names[weekday]}曜日",
        "scheduler_alive": scheduler_alive,
        "last_heartbeat": last_heartbeat,
        "emergency_stop": emergency_stop,
        "plans": plan_statuses,
    }


def _safe_int(v):
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


@router.get("/dashboard")
async def get_dashboard(db: Session = Depends(get_db), _=Depends(require_admin)):
    """ダッシュボード統計"""
    today = _today_jst()

    # 有効プラン数
    active_plans = db.query(Plan).filter(Plan.is_active == True).count()

    # 今日の進捗ステータス別
    today_items = db.query(ProgressPlan).filter(ProgressPlan.date == today).all()
    running = sum(1 for p in today_items if p.status == 1)
    completed = sum(1 for p in today_items if p.status == 2)
    errors = sum(1 for p in today_items if p.status == 3)

    # 今日の配信統計
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    today_dels = db.query(Delivery).filter(
        Delivery.created_at >= today_start,
        Delivery.created_at <= today_end,
    ).all()
    today_deliveries = len(today_dels)
    today_success = sum(d.success_count or 0 for d in today_dels)
    today_fail = sum(d.fail_count or 0 for d in today_dels)
    today_total_sent = sum(d.total_count or 0 for d in today_dels)

    # スケジューラー (有効プランの配信予定)
    schedule_type_label = {"daily": "毎日", "weekday": "曜日指定", "sheets": "シート連動"}
    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    active_plan_list = db.query(Plan).filter(Plan.is_active == True).order_by(Plan.sort_order.asc()).all()
    schedules = []
    for pl in active_plan_list:
        wd_str = ""
        if pl.schedule_type == "weekday" and pl.schedule_weekdays:
            try:
                wd_str = ", ".join(weekday_names[int(d)] for d in pl.schedule_weekdays if int(d) < 7)
            except (ValueError, TypeError, IndexError):
                wd_str = ""
        # 今日の進捗状態
        today_pp = next((tp for tp in today_items if tp.plan_id == pl.id), None)
        schedules.append({
            "plan_name": pl.name,
            "schedule_type": schedule_type_label.get(pl.schedule_type, pl.schedule_type or "-"),
            "send_time": pl.send_time.strftime("%H:%M") if pl.send_time else "-",
            "weekdays": wd_str,
            "today_status": today_pp.status if today_pp else None,
        })

    # 最近のエラー (直近5件)
    error_items = db.query(ProgressPlan, Plan.name).join(
        Plan, ProgressPlan.plan_id == Plan.id, isouter=True
    ).filter(
        ProgressPlan.status == 3,
    ).order_by(ProgressPlan.updated_at.desc()).limit(5).all()

    recent_errors = []
    for pp, plan_name in error_items:
        error_message = ""
        if pp.delivery_id:
            fail_item = db.query(DeliveryItem).filter(
                DeliveryItem.delivery_id == pp.delivery_id,
                DeliveryItem.status == 3,
            ).first()
            if fail_item:
                error_message = fail_item.last_error_message or ""
        recent_errors.append({
            "plan_name": plan_name or "(削除済)",
            "error_message": error_message,
            "created_at": _to_jst_iso(pp.updated_at),
        })

    return {
        "active_plans": active_plans,
        "running": running,
        "completed": completed,
        "errors": errors,
        "today_deliveries": today_deliveries,
        "today_success": today_success,
        "today_fail": today_fail,
        "today_total_sent": today_total_sent,
        "emergency_stop": check_emergency_stop(),
        "schedules": schedules,
        "recent_errors": recent_errors,
    }


@router.get("")
async def list_progress(
    target_date: date = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """進捗一覧 (配信集計情報付き)"""
    if not target_date:
        target_date = _today_jst()

    items = db.query(ProgressPlan).filter(
        ProgressPlan.date == target_date,
    ).order_by(ProgressPlan.created_at.desc()).all()

    # ProgressPlan が存在するplan_idセット
    existing_plan_ids = {p.plan_id for p in items}

    result = []
    for p in items:
        plan = db.query(Plan).filter(Plan.id == p.plan_id).first()

        # 配信の集計情報
        total_items = 0
        success_count = 0
        fail_count = 0
        delivery_subject = None
        delivery_started_at = None
        delivery_completed_at = None
        delivery_status = None
        duration_seconds = None

        if p.delivery_id:
            delivery = db.query(Delivery).filter(Delivery.id == p.delivery_id).first()
            if delivery:
                total_items = delivery.total_count
                success_count = delivery.success_count
                fail_count = delivery.fail_count
                delivery_subject = delivery.subject
                delivery_status = delivery.status
                delivery_started_at = _jst_iso(delivery.started_at)
                delivery_completed_at = _jst_iso(delivery.completed_at)
                if delivery.started_at and delivery.completed_at:
                    duration_seconds = int((delivery.completed_at - delivery.started_at).total_seconds())

        # スケジュール情報
        schedule_time = plan.send_time.strftime("%H:%M") if plan and plan.send_time else None
        schedule_type_label = {"daily": "毎日", "weekday": "曜日指定", "sheets": "シート連動"}

        result.append({
            "id": p.id,
            "plan_id": p.plan_id,
            "plan_name": plan.name if plan else "(削除済)",
            "date": p.date.isoformat(),
            "send_type": p.send_type,
            "status": p.status,
            "status_label": STATUS_LABELS.get(p.status, "不明"),
            "delivery_id": p.delivery_id,
            "total_items": total_items,
            "success_count": success_count,
            "fail_count": fail_count,
            "delivery_subject": delivery_subject,
            "delivery_status": delivery_status,
            "delivery_started_at": delivery_started_at,
            "delivery_completed_at": delivery_completed_at,
            "duration_seconds": duration_seconds,
            "schedule_type": schedule_type_label.get(plan.schedule_type, plan.schedule_type or "-") if plan else "-",
            "schedule_time": schedule_time,
            "updated_at": _to_jst_iso(p.updated_at),
        })

    # ProgressPlan がまだない有効プランを「待機中」として追加
    schedule_type_label = {"daily": "毎日", "weekday": "曜日指定", "sheets": "シート連動"}
    active_plans = db.query(Plan).filter(Plan.is_active == True).order_by(Plan.sort_order.asc()).all()
    for pl in active_plans:
        if pl.id in existing_plan_ids:
            continue
        result.append({
            "id": None,
            "plan_id": pl.id,
            "plan_name": pl.name,
            "date": target_date.isoformat(),
            "send_type": "scheduled",
            "status": -1,
            "status_label": "待機中",
            "delivery_id": None,
            "total_items": 0,
            "success_count": 0,
            "fail_count": 0,
            "delivery_subject": None,
            "delivery_status": None,
            "delivery_started_at": None,
            "delivery_completed_at": None,
            "duration_seconds": None,
            "schedule_type": schedule_type_label.get(pl.schedule_type, pl.schedule_type or "-"),
            "schedule_time": pl.send_time.strftime("%H:%M") if pl.send_time else None,
            "updated_at": None,
        })

    return {
        "date": target_date.isoformat(),
        "emergency_stop": check_emergency_stop(),
        "items": result,
    }


@router.get("/{progress_id}/detail")
async def get_progress_detail(
    progress_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """進捗詳細 (ユーザー別配信結果)"""
    pp = db.query(ProgressPlan).filter(ProgressPlan.id == progress_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="進捗データが見つかりません")

    plan = db.query(Plan).filter(Plan.id == pp.plan_id).first()

    delivery_data = None
    items_data = []

    if pp.delivery_id:
        delivery = db.query(Delivery).filter(Delivery.id == pp.delivery_id).first()
        if delivery:
            delivery_data = {
                "id": delivery.id,
                "subject": delivery.subject,
                "total_count": delivery.total_count,
                "success_count": delivery.success_count,
                "fail_count": delivery.fail_count,
                "started_at": _jst_iso(delivery.started_at),
                "completed_at": _jst_iso(delivery.completed_at),
                "status": delivery.status,
            }

            # DeliveryItem一覧
            di_rows = db.query(DeliveryItem, User).join(
                User, DeliveryItem.user_id == User.id, isouter=True
            ).filter(
                DeliveryItem.delivery_id == delivery.id,
            ).order_by(DeliveryItem.id).all()

            for di, user in di_rows:
                items_data.append({
                    "user_name": f"{user.name_last} {user.name_first}" if user else "(削除済み)",
                    "member_no": di.member_no_snapshot,
                    "email": user.email if user else "-",
                    "status": di.status,
                    "sent_at": _jst_iso(di.sent_at),
                    "error_message": di.last_error_message,
                })

    return {
        "plan_name": plan.name if plan else "(削除済)",
        "status": pp.status,
        "delivery": delivery_data,
        "items": items_data,
    }


@router.post("/{progress_id}/reset")
async def reset_progress(progress_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """進捗リセット (status→0, delivery紐付け解除, 実行中delivery停止)"""
    p = db.query(ProgressPlan).filter(ProgressPlan.id == progress_id).first()
    if p:
        # 紐づくdeliveryが実行中なら停止にする
        if p.delivery_id:
            delivery = db.query(Delivery).filter(Delivery.id == p.delivery_id).first()
            if delivery and delivery.status == "running":
                delivery.status = "stopped"
                delivery.completed_at = datetime.now(ZoneInfo("Asia/Tokyo"))
        p.status = 0
        p.delivery_id = None
        db.commit()
    return {"message": "リセットしました"}


@router.post("/emergency-stop")
async def toggle_emergency_stop(active: bool, _=Depends(require_admin)):
    """緊急停止フラグ切替"""
    set_emergency_stop(active)
    return {"message": f"緊急停止を{'有効' if active else '解除'}にしました", "active": active}


@router.post("/{progress_id}/retry-failed")
async def retry_failed_progress(progress_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """失敗したユーザーにのみ再送（進捗管理画面用）"""
    from app.services.delivery_service import retry_failed_delivery

    pp = db.query(ProgressPlan).filter(ProgressPlan.id == progress_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="進捗データが見つかりません")

    if not pp.delivery_id:
        raise HTTPException(status_code=400, detail="配信履歴がありません")

    # 失敗件数を確認
    failed_count = db.query(DeliveryItem).filter(
        DeliveryItem.delivery_id == pp.delivery_id,
        DeliveryItem.status == 3,
    ).count()

    if failed_count == 0:
        return {"message": "再送対象の失敗ユーザーがいません", "retried": 0, "success": 0, "failed": 0}

    result = retry_failed_delivery(db, pp.delivery_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
