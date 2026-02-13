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


def watchdog():
    """
    Watchdog: ハング検出と障害復旧

    検出条件:
    - status=1 (RUNNING) で heartbeat_at が古い → プロセス死亡と判断
    - status=3 (ERROR) で retry_count < max_retries → 自動リトライ対象

    復旧アクション:
    - retry_count < max_retries → status=0 (PENDING) にリセット
    - retry_count >= max_retries → アラート通知（手動介入要）
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from app.core.database import SessionLocal
    from app.models.progress_plan import ProgressPlan
    from app.services.report_service import send_error_alert

    JST = ZoneInfo("Asia/Tokyo")
    HEARTBEAT_TIMEOUT_MINUTES = 15  # heartbeatがこれより古いとハング判定
    
    db = SessionLocal()
    try:
        now = datetime.now(JST)
        threshold = now - timedelta(minutes=HEARTBEAT_TIMEOUT_MINUTES)

        # 1. status=1 でheartbeatが古い（ハング）
        hung_tasks = db.query(ProgressPlan).filter(
            ProgressPlan.status == 1,
            ProgressPlan.heartbeat_at < threshold,
        ).all()

        for p in hung_tasks:
            p.retry_count += 1
            
            if p.retry_count < p.max_retries:
                # リトライ可能 → PENDINGにリセット
                logger.warning(
                    f"ハング検出→リトライ: progress_id={p.id}, plan_id={p.plan_id}, "
                    f"retry={p.retry_count}/{p.max_retries}"
                )
                p.status = 0  # PENDING
                p.last_error = f"Watchdog: heartbeat timeout ({HEARTBEAT_TIMEOUT_MINUTES}min)"
            else:
                # リトライ上限 → ERRORのまま、アラート送信
                logger.error(
                    f"ハング検出→リトライ上限: progress_id={p.id}, plan_id={p.plan_id}, "
                    f"retry={p.retry_count}/{p.max_retries}"
                )
                p.status = 3  # ERROR
                p.last_error = f"Watchdog: max retries exceeded after heartbeat timeout"
                
                # アラート送信
                try:
                    send_error_alert(
                        plan_id=p.plan_id,
                        plan_name=f"Plan ID: {p.plan_id}",
                        error_message=f"Watchdog: 最大リトライ回数超過 ({p.retry_count}/{p.max_retries})",
                        details={
                            "progress_id": p.id,
                            "last_heartbeat": p.heartbeat_at.isoformat() if p.heartbeat_at else None,
                        }
                    )
                except Exception as alert_err:
                    logger.error(f"Watchdogアラート送信失敗: {alert_err}")
            
            p.heartbeat_at = now
            p.updated_at = now

        db.commit()

        if hung_tasks:
            logger.info(f"Watchdog: {len(hung_tasks)}件のハングタスクを処理")

    except Exception as e:
        logger.error(f"Watchdogエラー: {e}")
    finally:
        db.close()


# 後方互換性のためのエイリアス
hang_detector = watchdog


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
