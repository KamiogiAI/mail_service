"""日次レポート・エラーアラートサービス

仕様:
- 日次レポート: 毎日 23:55 JST に全管理者へ送信
- エラーアラート: エラー発生時に即時送信

件名フォーマット:
- [正常] 日次レポート YYYY-MM-DD
- [警告] 日次レポート YYYY-MM-DD (一部エラーあり)
- [異常] 日次レポート YYYY-MM-DD (失敗あり)
- 日次レポート YYYY-MM-DD（実行なし）
"""
from datetime import datetime, timedelta, time, date
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import resend

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.api_keys import get_resend_api_key, get_from_email, get_site_name
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.models.plan import Plan
from app.models.user import User
from app.models.system_log import SystemLog
from app.models.report_delivery import ReportDelivery
from app.models.report_delivery_item import ReportDeliveryItem
from app.core.logging import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")

# 最後にレポート送信した日付（1日1回制限用）
_last_report_date: date = None

template_dir = Path(__file__).parent.parent / "templates" / "email"
jinja_env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(["html"]),
)


def generate_daily_report(db: Session, report_date: datetime.date = None) -> dict:
    """日次レポートデータ生成"""
    if not report_date:
        report_date = datetime.now(JST).date()

    day_start = datetime.combine(report_date, time.min).replace(tzinfo=JST)
    day_end = datetime.combine(report_date, time.max).replace(tzinfo=JST)

    # 当日の配信集計
    deliveries = db.query(Delivery).filter(
        Delivery.created_at >= day_start,
        Delivery.created_at <= day_end,
    ).all()

    total_deliveries = len(deliveries)
    total_success = sum(d.success_count for d in deliveries)
    total_fail = sum(d.fail_count for d in deliveries)
    total_sent = sum(d.total_count for d in deliveries)

    # プラン別集計
    plan_stats = {}
    for d in deliveries:
        plan = db.query(Plan).filter(Plan.id == d.plan_id).first()
        plan_name = plan.name if plan else f"(ID:{d.plan_id})"
        if plan_name not in plan_stats:
            plan_stats[plan_name] = {"sent": 0, "success": 0, "fail": 0}
        plan_stats[plan_name]["sent"] += d.total_count
        plan_stats[plan_name]["success"] += d.success_count
        plan_stats[plan_name]["fail"] += d.fail_count

    # 失敗・停止一覧
    failed_deliveries = [d for d in deliveries if d.status in ("failed", "partial_failed", "stopped")]

    # エラー/警告集計
    error_count = db.query(SystemLog).filter(
        SystemLog.created_at >= day_start,
        SystemLog.created_at <= day_end,
        SystemLog.level.in_(["ERROR", "CRITICAL"]),
    ).count()

    warning_count = db.query(SystemLog).filter(
        SystemLog.created_at >= day_start,
        SystemLog.created_at <= day_end,
        SystemLog.level == "WARNING",
    ).count()

    # ステータス判定
    if total_fail > 0 or len(failed_deliveries) > 0:
        status = "error"  # 異常
    elif error_count > 0 or warning_count > 0:
        status = "warning"  # 警告
    elif total_deliveries == 0:
        status = "none"  # 実行なし
    else:
        status = "ok"  # 正常

    return {
        "report_date": report_date.isoformat(),
        "total_deliveries": total_deliveries,
        "total_sent": total_sent,
        "total_success": total_success,
        "total_fail": total_fail,
        "plan_stats": plan_stats,
        "failed_count": len(failed_deliveries),
        "error_count": error_count,
        "warning_count": warning_count,
        "status": status,
    }


def _get_subject_prefix(status: str) -> str:
    """ステータスに応じた件名プレフィックス"""
    if status == "error":
        return "[異常]"
    elif status == "warning":
        return "[警告]"
    elif status == "none":
        return ""  # 実行なしは特別表記
    return "[正常]"


def send_daily_report(force: bool = False):
    """
    日次レポートを全管理者に送信

    Args:
        force: True の場合、1日1回制限を無視
    """
    global _last_report_date

    db = SessionLocal()
    try:
        report_date = datetime.now(JST).date()

        # 1日1回制限（メモリ上でトラッキング）
        if not force and _last_report_date == report_date:
            logger.debug(f"レポート送信済み (メモリ): {report_date}")
            return

        # DB上でも確認
        existing = db.query(ReportDelivery).filter(
            ReportDelivery.report_date == report_date
        ).first()
        if not force and existing and existing.status == 2:
            _last_report_date = report_date
            logger.info(f"レポート送信済み: {report_date}")
            return

        # レポートデータ生成
        report_data = generate_daily_report(db, report_date)

        # 管理者一覧
        admins = db.query(User).filter(
            User.role == "admin",
            User.is_active == True,
        ).all()

        if not admins:
            logger.info("レポート送信対象の管理者がいません")
            return

        # ReportDeliveryレコード作成
        if not existing:
            report_delivery = ReportDelivery(
                report_date=report_date,
                status=1,
                total_admins=len(admins),
            )
            db.add(report_delivery)
            db.commit()
            db.refresh(report_delivery)
        else:
            report_delivery = existing
            report_delivery.status = 1
            report_delivery.retry_count += 1
            db.commit()

        # HTMLレポート生成
        template = jinja_env.get_template("daily_report.html")
        site_name = get_site_name()
        html = template.render(
            site_name=site_name,
            **report_data,
        )

        # 件名生成
        status = report_data.get("status", "ok")
        prefix = _get_subject_prefix(status)
        if status == "none":
            subject = f"【{site_name}】日次レポート {report_date}（実行なし）"
        else:
            subject = f"【{site_name}】{prefix} 日次レポート {report_date}"

        # 各管理者に送信
        success_count = 0
        fail_count = 0

        resend.api_key = get_resend_api_key()

        for admin in admins:
            item = ReportDeliveryItem(
                report_delivery_id=report_delivery.id,
                admin_user_id=admin.id,
                status=1,
            )
            db.add(item)
            db.commit()

            try:
                resend.Emails.send({
                    "from": get_from_email(),
                    "to": [admin.email],
                    "subject": subject,
                    "html": html,
                })
                item.status = 2
                item.sent_at = datetime.now(JST)
                success_count += 1
            except Exception as e:
                item.status = 3
                item.last_error = str(e)
                fail_count += 1
                logger.error(f"レポート送信失敗: admin_id={admin.id} - {e}")

            db.commit()

        # 完了更新
        report_delivery.success_count = success_count
        report_delivery.fail_count = fail_count
        report_delivery.status = 2 if fail_count == 0 else 3
        db.commit()

        _last_report_date = report_date
        logger.info(f"日次レポート送信完了: date={report_date}, status={status}, success={success_count}, fail={fail_count}")

    except Exception as e:
        logger.error(f"日次レポート生成エラー: {e}")
    finally:
        db.close()


def try_send_daily_report():
    """
    23:55 JST 以降かつ1日1回のみ送信。
    スケジューラーから毎分呼ばれる想定。
    """
    now = datetime.now(JST)
    if now.hour == 23 and now.minute >= 55:
        send_daily_report()


def send_error_alert(
    plan_id: int = None,
    plan_name: str = None,
    error_message: str = "",
    details: dict = None,
):
    """
    エラーアラートを全管理者に即時送信

    Args:
        plan_id: プランID
        plan_name: プラン名
        error_message: エラーメッセージ
        details: 追加詳細情報
    """
    db = SessionLocal()
    try:
        # 管理者一覧
        admins = db.query(User).filter(
            User.role == "admin",
            User.is_active == True,
        ).all()

        if not admins:
            logger.warning("エラーアラート送信対象の管理者がいません")
            return

        site_name = get_site_name()
        now = datetime.now(JST)

        # 件名
        if plan_name:
            subject = f"【{site_name}】[エラー] {plan_name}"
        else:
            subject = f"【{site_name}】[エラー] システムエラー"

        # HTML生成
        html = _generate_error_alert_html(
            site_name=site_name,
            plan_id=plan_id,
            plan_name=plan_name,
            error_message=error_message,
            details=details,
            occurred_at=now,
        )

        resend.api_key = get_resend_api_key()

        for admin in admins:
            try:
                resend.Emails.send({
                    "from": get_from_email(),
                    "to": [admin.email],
                    "subject": subject,
                    "html": html,
                })
                logger.info(f"エラーアラート送信: admin_id={admin.id}, plan_id={plan_id}")
            except Exception as e:
                logger.error(f"エラーアラート送信失敗: admin_id={admin.id} - {e}")

    except Exception as e:
        logger.error(f"エラーアラート生成エラー: {e}")
    finally:
        db.close()


def _generate_error_alert_html(
    site_name: str,
    plan_id: int,
    plan_name: str,
    error_message: str,
    details: dict,
    occurred_at: datetime,
) -> str:
    """エラーアラートHTMLを生成"""
    details_html = ""
    if details:
        details_html = "<h3 style='margin-top: 20px;'>詳細情報</h3><ul>"
        for key, value in details.items():
            details_html += f"<li><strong>{key}:</strong> {value}</li>"
        details_html += "</ul>"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 700px; margin: 0 auto; padding: 20px; color: #333;">
    <div style="background: #dc3545; color: #fff; padding: 15px 20px; margin-bottom: 20px;">
        <h2 style="margin: 0;">⚠ エラーアラート</h2>
    </div>

    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr>
            <td style="padding: 10px; font-weight: bold; width: 120px; border-bottom: 1px solid #eee;">発生時刻</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">{occurred_at.strftime('%Y-%m-%d %H:%M:%S')}</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold; border-bottom: 1px solid #eee;">プラン</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">{plan_name or '-'} (ID: {plan_id or '-'})</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold; border-bottom: 1px solid #eee;">エラー内容</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; color: #dc3545;">{error_message}</td>
        </tr>
    </table>

    {details_html}

    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="color: #999; font-size: 12px;">{site_name} - エラーアラート</p>
</body>
</html>"""
