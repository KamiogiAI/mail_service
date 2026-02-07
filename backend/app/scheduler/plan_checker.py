"""毎分: 送信対象プランチェック + 日次レポート"""
from datetime import datetime, date
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.redis import get_sync_redis
from app.models.plan import Plan
from app.models.progress_plan import ProgressPlan
from app.services.sheets_service import is_today_in_sheets
from app.services.report_service import try_send_daily_report
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def check_plans():
    """送信時刻に一致するプランを検出し、progress_planを作成"""
    now = datetime.now(JST)
    current_time_str = now.strftime("%H:%M")
    today = now.date()
    weekday = now.weekday()  # 0=月〜6=日

    # ハートビート書き込み
    redis = get_sync_redis()
    redis.set("scheduler:heartbeat", now.isoformat(), ex=180)

    # 日次レポート送信チェック (23:55 JST)
    try:
        try_send_daily_report()
    except Exception as e:
        logger.error(f"日次レポート送信エラー: {e}")

    # 緊急停止チェック
    if redis.get("emergency_stop"):
        logger.info("緊急停止中: プランチェックスキップ")
        return

    db = SessionLocal()
    try:
        plans = db.query(Plan).filter(Plan.is_active == True).all()

        for plan in plans:
            if not plan.send_time:
                continue

            plan_time_str = plan.send_time.strftime("%H:%M")
            if plan_time_str != current_time_str:
                continue

            # スケジュール条件チェック
            if not _should_send_today(plan, today, weekday):
                continue

            # 重複チェック: 今日の定時送信が既に存在するか
            existing = db.query(ProgressPlan).filter(
                ProgressPlan.plan_id == plan.id,
                ProgressPlan.date == today,
                ProgressPlan.send_type == "scheduled",
            ).first()

            if existing:
                continue

            # progress_plan作成 (status=0: 未実行)
            progress = ProgressPlan(
                plan_id=plan.id,
                date=today,
                send_type="scheduled",
                status=0,
            )
            db.add(progress)
            db.commit()
            logger.info(f"送信タスク作成: plan_id={plan.id}, date={today}")

    except Exception as e:
        logger.error(f"プランチェックエラー: {e}")
    finally:
        db.close()


def _should_send_today(plan: Plan, today: date, weekday: int) -> bool:
    """今日送信すべきか判定"""
    if plan.schedule_type == "daily":
        return True
    elif plan.schedule_type == "weekday":
        if plan.schedule_weekdays and weekday in plan.schedule_weekdays:
            return True
        return False
    elif plan.schedule_type == "sheets":
        if plan.sheets_id:
            return is_today_in_sheets(plan.sheets_id)
        return False
    return False
