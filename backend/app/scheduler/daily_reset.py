"""00:00 JST: 日次クリーンアップ"""
from datetime import datetime
from zoneinfo import ZoneInfo
from app.core.database import SessionLocal
from app.models.progress_plan import ProgressPlan
from app.models.progress_task import ProgressTask
from app.models.delivery import Delivery
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def daily_reset():
    """
    日次クリーンアップ:
    - 完了済み (status=2) はリセット不要 (スケジューラーが毎日新しいレコードを作る)
    - 実行中のまま残った (status=1) をエラーに変更
    - running のまま残った delivery を stopped に変更
    """
    db = SessionLocal()
    now = datetime.now(JST)
    try:
        # status=1 (実行中) のまま日をまたいだタスクをエラーに
        hung_plans = db.query(ProgressPlan).filter(
            ProgressPlan.status == 1,
        ).update({"status": 3})

        hung_tasks = db.query(ProgressTask).filter(
            ProgressTask.status == 1,
        ).update({"status": 3})

        # running のまま残った delivery を stopped に
        stale_deliveries = db.query(Delivery).filter(
            Delivery.status == "running",
        ).all()
        for d in stale_deliveries:
            d.status = "stopped"
            d.completed_at = now

        db.commit()
        logger.info(
            f"日次クリーンアップ完了: hung_plans={hung_plans}, "
            f"hung_tasks={hung_tasks}, stale_deliveries={len(stale_deliveries)}"
        )
    except Exception as e:
        logger.error(f"日次クリーンアップエラー: {e}")
        db.rollback()
    finally:
        db.close()
