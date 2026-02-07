"""タスク処理ループ"""
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import and_

from app.core.database import SessionLocal
from app.models.plan import Plan
from app.models.progress_plan import ProgressPlan
from app.services.delivery_service import execute_plan_delivery
from app.services.report_service import send_error_alert
from app.worker.throttle_manager import check_emergency_stop, get_throttle_sleep
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")
MAX_RETRY = 3


def process_pending_tasks():
    """
    未実行タスクを処理する。

    優先順位: 3(エラーリトライ) → 1(ハング復帰) → 0(通常)
    """
    if check_emergency_stop():
        logger.info("緊急停止中: タスク処理スキップ")
        return False

    db = SessionLocal()
    try:
        # 優先順位順に1件取得
        progress = _get_next_task(db)
        if not progress:
            return False

        plan = db.query(Plan).filter(Plan.id == progress.plan_id).first()
        if not plan:
            progress.status = 3
            db.commit()
            return True

        # 実行中に更新
        progress.status = 1
        db.commit()

        logger.info(f"タスク実行開始: progress_id={progress.id}, plan_id={plan.id}")

        try:
            throttle = get_throttle_sleep()
            delivery = execute_plan_delivery(
                db=db,
                plan=plan,
                send_type=progress.send_type,
                throttle_seconds=throttle,
            )

            if delivery:
                progress.delivery_id = delivery.id
                progress.status = 2  # 完了
            else:
                progress.status = 2  # 対象ユーザーなし = 完了扱い

            db.commit()
            logger.info(f"タスク実行完了: progress_id={progress.id}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"タスク実行エラー: progress_id={progress.id} - {error_msg}")
            db.rollback()
            db = SessionLocal()
            progress = db.query(ProgressPlan).filter(ProgressPlan.id == progress.id).first()
            if progress:
                progress.status = 3  # エラー
                db.commit()

            # エラーアラート送信
            try:
                send_error_alert(
                    plan_id=plan.id,
                    plan_name=plan.name,
                    error_message=error_msg,
                    details={
                        "progress_id": progress.id if progress else None,
                        "send_type": progress.send_type if progress else None,
                    }
                )
            except Exception as alert_err:
                logger.error(f"エラーアラート送信失敗: {alert_err}")

        return True

    except Exception as e:
        logger.error(f"タスク処理エラー: {e}")
        return False
    finally:
        db.close()


def _get_next_task(db) -> ProgressPlan:
    """優先順位に基づいて次のタスクを取得"""
    now = datetime.now(JST)
    today = now.date()
    hang_threshold = now - timedelta(minutes=30)

    # 1: ハングタスク (status=1で30分以上経過) → status=0にリセットして再処理
    hung_task = db.query(ProgressPlan).filter(
        ProgressPlan.status == 1,
        ProgressPlan.date == today,
        ProgressPlan.updated_at < hang_threshold.replace(tzinfo=None),
    ).first()
    if hung_task:
        logger.warning(f"ハングタスク検出: progress_id={hung_task.id}, リセットして再処理")
        hung_task.status = 0
        db.commit()
        return hung_task

    # 3: エラー (リトライ回数制限内)
    task = db.query(ProgressPlan).filter(
        ProgressPlan.status == 3,
        ProgressPlan.date == today,
    ).first()
    if task:
        return task

    # 0: 通常 (未実行)
    task = db.query(ProgressPlan).filter(
        ProgressPlan.status == 0,
        ProgressPlan.date == today,
    ).first()
    return task
