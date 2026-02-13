"""タスク処理ループ"""
import time
from datetime import datetime
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


def process_pending_tasks():
    """
    未実行タスクを処理する。

    優先順位: 3(エラーリトライ、retry_count < max_retries) → 0(通常)
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
            progress.last_error = "Plan not found"
            progress.updated_at = datetime.now(JST)
            db.commit()
            return True

        # ロック取得: 実行中に更新
        now = datetime.now(JST)
        progress.status = 1
        progress.heartbeat_at = now
        progress.updated_at = now
        progress.last_error = None  # エラーをクリア
        db.commit()

        logger.info(f"タスク実行開始: progress_id={progress.id}, plan_id={plan.id}, retry={progress.retry_count}")

        try:
            throttle = get_throttle_sleep()
            delivery = execute_plan_delivery(
                db=db,
                plan=plan,
                send_type=progress.send_type,
                throttle_seconds=throttle,
                progress_id=progress.id,
                cursor=progress.cursor,  # 途中再開用
            )

            if delivery:
                progress.delivery_id = delivery.id
                progress.status = 2  # 完了
                progress.cursor = None  # 完了したらcursorクリア
            else:
                progress.status = 2  # 対象ユーザーなし = 完了扱い
                progress.cursor = None

            now = datetime.now(JST)
            progress.heartbeat_at = now
            progress.updated_at = now
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
                progress.retry_count += 1
                progress.last_error = error_msg[:1000]  # 最大1000文字
                progress.updated_at = datetime.now(JST)
                db.commit()

                # max_retriesを超えた場合のみアラート送信
                if progress.retry_count >= progress.max_retries:
                    try:
                        send_error_alert(
                            plan_id=plan.id,
                            plan_name=plan.name,
                            error_message=f"最大リトライ回数超過 ({progress.retry_count}/{progress.max_retries}): {error_msg}",
                            details={
                                "progress_id": progress.id,
                                "send_type": progress.send_type,
                                "retry_count": progress.retry_count,
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


def update_heartbeat(db, progress_id: int) -> bool:
    """
    ハートビートを更新する。
    長時間処理中にWorkerから呼び出す。
    """
    try:
        progress = db.query(ProgressPlan).filter(ProgressPlan.id == progress_id).first()
        if progress and progress.status == 1:
            progress.heartbeat_at = datetime.now(JST)
            db.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Heartbeat更新エラー: {e}")
        return False


def update_cursor(db, progress_id: int, cursor: str) -> bool:
    """
    cursorを更新する（途中再開用）。
    各アイテム処理後にWorkerから呼び出す。
    """
    try:
        progress = db.query(ProgressPlan).filter(ProgressPlan.id == progress_id).first()
        if progress and progress.status == 1:
            progress.cursor = cursor
            progress.heartbeat_at = datetime.now(JST)
            db.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Cursor更新エラー: {e}")
        return False


def _get_next_task(db) -> ProgressPlan:
    """
    優先順位に基づいて次のタスクを取得。

    優先順位:
    1. status=3 (エラー) かつ retry_count < max_retries → リトライ対象
    2. status=0 (未実行) → 通常実行
    """
    today = datetime.now(JST).date()

    # 1. エラー状態でリトライ可能なもの
    task = db.query(ProgressPlan).filter(
        ProgressPlan.status == 3,
        ProgressPlan.date == today,
        ProgressPlan.retry_count < ProgressPlan.max_retries,
    ).first()
    if task:
        logger.info(f"リトライ対象タスク検出: progress_id={task.id}, retry={task.retry_count}/{task.max_retries}")
        return task

    # 2. 未実行
    task = db.query(ProgressPlan).filter(
        ProgressPlan.status == 0,
        ProgressPlan.date == today,
    ).first()
    return task
