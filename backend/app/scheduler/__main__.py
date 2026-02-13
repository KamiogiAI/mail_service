"""Scheduler エントリポイント: python -m app.scheduler で起動"""
import signal
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import setup_logging, get_logger
from app.scheduler.plan_checker import check_plans
from app.scheduler.daily_reset import daily_reset

setup_logging()
logger = get_logger("scheduler")

scheduler = BlockingScheduler(timezone="Asia/Tokyo")


def signal_handler(sig, frame):
    logger.info("Scheduler停止シグナル受信")
    scheduler.shutdown(wait=False)
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def hang_detector():
    """15分超のstatus=1を検出・リセット"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from app.core.database import SessionLocal
    from app.models.progress_plan import ProgressPlan

    JST = ZoneInfo("Asia/Tokyo")
    db = SessionLocal()
    try:
        threshold = datetime.now(JST) - timedelta(minutes=15)
        hung = db.query(ProgressPlan).filter(
            ProgressPlan.status == 1,
            ProgressPlan.updated_at < threshold,
        ).all()

        for p in hung:
            logger.warning(f"ハング検出: progress_plan id={p.id}, plan_id={p.plan_id}")
            p.status = 0
            p.updated_at = datetime.now(JST)
        db.commit()
    except Exception as e:
        logger.error(f"ハング検知エラー: {e}")
    finally:
        db.close()


def main():
    logger.info("Scheduler起動")

    # 毎分: プランチェック
    scheduler.add_job(
        check_plans,
        CronTrigger(minute="*", timezone="Asia/Tokyo"),
        id="plan_checker",
        max_instances=1,
    )

    # 5分ごと: ハング検知
    scheduler.add_job(
        hang_detector,
        CronTrigger(minute="*/5", timezone="Asia/Tokyo"),
        id="hang_detector",
        max_instances=1,
    )

    # 00:00 JST: 日次リセット
    scheduler.add_job(
        daily_reset,
        CronTrigger(hour=0, minute=0, timezone="Asia/Tokyo"),
        id="daily_reset",
        max_instances=1,
    )

    # 5分ごと: ダウングレード予約適用
    from app.scheduler.plan_change_applier import apply_pending_plan_changes
    scheduler.add_job(
        apply_pending_plan_changes,
        CronTrigger(minute="*/5", timezone="Asia/Tokyo"),
        id="plan_change_applier",
        max_instances=1,
    )

    # 23:55 JST: 日次レポート
    from app.scheduler.daily_report import daily_report_job
    scheduler.add_job(
        daily_report_job,
        CronTrigger(hour=23, minute=55, timezone="Asia/Tokyo"),
        id="daily_report",
        max_instances=1,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler終了")


if __name__ == "__main__":
    main()
else:
    main()
