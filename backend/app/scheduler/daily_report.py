"""23:55 JSTトリガー: 日次レポート送信"""
from app.services.report_service import send_daily_report
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_RETRY = 3
RETRY_INTERVAL_MINUTES = 5


def daily_report_job():
    """日次レポート送信ジョブ"""
    logger.info("日次レポート送信開始")
    try:
        send_daily_report()
    except Exception as e:
        logger.error(f"日次レポート送信エラー: {e}")
