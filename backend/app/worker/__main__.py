"""Worker エントリポイント: python -m app.worker で起動"""
import time
import signal
import sys
from app.core.logging import setup_logging, get_logger
from app.worker.task_processor import process_pending_tasks
from app.worker.throttle_manager import check_emergency_stop

setup_logging()
logger = get_logger("worker")

running = True


def signal_handler(sig, frame):
    global running
    logger.info("Worker停止シグナル受信")
    running = False


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def main():
    logger.info("Worker起動")
    while running:
        try:
            if check_emergency_stop():
                logger.debug("緊急停止中: 待機")
                time.sleep(10)
                continue

            had_task = process_pending_tasks()
            if not had_task:
                # タスクなし: 5秒待機
                time.sleep(5)
        except Exception as e:
            logger.error(f"Workerループエラー: {e}")
            time.sleep(10)

    logger.info("Worker終了")


if __name__ == "__main__":
    main()
else:
    main()
