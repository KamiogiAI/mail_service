"""日次レポートメール送信サービス"""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.user import User
from app.models.plan import Plan
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.models.progress_plan import ProgressPlan
from app.models.system_log import SystemLog
from app.services.resend_service import send_email

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def generate_daily_report_html(db: Session, target_date: date) -> str:
    """日次レポートのHTML生成"""
    
    # 本日の配信データ取得
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    
    deliveries = db.query(Delivery).filter(
        Delivery.started_at >= start_of_day,
        Delivery.started_at <= end_of_day,
    ).all()
    
    # 統計計算
    total_deliveries = len(deliveries)
    total_success = sum(d.success_count or 0 for d in deliveries)
    total_fail = sum(d.fail_count or 0 for d in deliveries)
    total_sent = total_success + total_fail
    
    # 全体ステータス判定
    if total_deliveries == 0:
        overall_status = "実行なし"
        status_color = "#6c757d"
    elif total_fail == 0:
        overall_status = "成功"
        status_color = "#28a745"
    elif total_success == 0:
        overall_status = "失敗"
        status_color = "#dc3545"
    else:
        overall_status = "一部失敗"
        status_color = "#ffc107"
    
    # プラン別結果
    plan_results = []
    for d in deliveries:
        plan = db.query(Plan).filter(Plan.id == d.plan_id).first()
        plan_name = plan.name if plan else "(手動送信)"
        
        # 所要時間計算
        duration = "-"
        if d.started_at and d.completed_at:
            sec = int((d.completed_at - d.started_at).total_seconds())
            if sec < 60:
                duration = f"{sec}秒"
            else:
                duration = f"{sec // 60}分{sec % 60}秒"
        
        result_text = "成功" if d.status == "success" else "一部失敗" if d.status == "partial_failed" else "失敗" if d.status == "failed" else d.status
        result_color = "#28a745" if d.status == "success" else "#ffc107" if d.status == "partial_failed" else "#dc3545"
        
        plan_results.append({
            "plan_name": plan_name,
            "result": result_text,
            "result_color": result_color,
            "count": (d.success_count or 0) + (d.fail_count or 0),
            "duration": duration,
        })
    
    # プラン進捗状況
    plans = db.query(Plan).filter(Plan.is_active == True).all()
    plan_status_list = []
    for plan in plans:
        progress = db.query(ProgressPlan).filter(
            ProgressPlan.plan_id == plan.id,
            ProgressPlan.date == target_date,
        ).first()
        
        status_text = "待機中"
        if progress:
            if progress.status == 2:
                status_text = "完了"
            elif progress.status == 1:
                status_text = "実行中"
            elif progress.status == 3:
                status_text = "エラー"
        
        plan_status_list.append({
            "plan_name": plan.name,
            "batch_enabled": "ON" if plan.batch_send_enabled else "OFF",
            "status": status_text,
        })
    
    # エラーログ取得 (ERROR, WARNING, CRITICALのみ)
    errors = db.query(SystemLog).filter(
        SystemLog.created_at >= start_of_day,
        SystemLog.created_at <= end_of_day,
        SystemLog.level.in_(["ERROR", "WARNING", "CRITICAL"]),
    ).order_by(SystemLog.created_at.desc()).limit(10).all()
    
    # HTML生成
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 8px; overflow: hidden; }}
        .header {{ background: #2c3e50; color: #fff; padding: 20px; }}
        .header h1 {{ margin: 0 0 5px 0; font-size: 20px; }}
        .header .date {{ opacity: 0.8; font-size: 14px; }}
        .status-bar {{ background: {status_color}; color: #fff; padding: 15px 20px; font-size: 16px; }}
        .content {{ padding: 20px; }}
        .stats {{ display: flex; justify-content: space-around; text-align: center; margin-bottom: 25px; }}
        .stat {{ }}
        .stat-value {{ font-size: 28px; font-weight: bold; }}
        .stat-value.success {{ color: #28a745; }}
        .stat-value.fail {{ color: #dc3545; }}
        .stat-label {{ font-size: 12px; color: #666; margin-top: 4px; }}
        .section {{ margin-bottom: 25px; }}
        .section-title {{ font-size: 16px; font-weight: 600; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 2px solid #3498db; }}
        .section-title.error {{ border-bottom-color: #dc3545; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 10px 8px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .empty {{ color: #999; text-align: center; padding: 20px; }}
        .footer {{ text-align: center; padding: 15px; color: #999; font-size: 12px; border-top: 1px solid #eee; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>サッカーご飯 日次レポート</h1>
            <div class="date">{target_date.strftime('%Y-%m-%d')}</div>
        </div>
        <div class="status-bar">全体ステータス: {overall_status}</div>
        <div class="content">
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{total_deliveries}</div>
                    <div class="stat-label">配信回数</div>
                </div>
                <div class="stat">
                    <div class="stat-value success">{total_success}</div>
                    <div class="stat-label">送信成功</div>
                </div>
                <div class="stat">
                    <div class="stat-value fail">{total_fail}</div>
                    <div class="stat-label">送信失敗</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{total_sent}</div>
                    <div class="stat-label">合計送信数</div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">プラン別実行結果</div>
                <table>
                    <thead><tr><th>プラン名</th><th>結果</th><th>送信数</th><th>所要時間</th></tr></thead>
                    <tbody>
    """
    
    if plan_results:
        for pr in plan_results:
            html += f"""
                        <tr>
                            <td>{pr['plan_name']}</td>
                            <td style="color:{pr['result_color']};font-weight:600;">{pr['result']}</td>
                            <td>{pr['count']}</td>
                            <td>{pr['duration']}</td>
                        </tr>
            """
    else:
        html += '<tr><td colspan="4" class="empty">本日の配信なし</td></tr>'
    
    html += """
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <div class="section-title">プラン進捗状況</div>
                <table>
                    <thead><tr><th>プラン名</th><th>一斉配信</th><th>ステータス</th></tr></thead>
                    <tbody>
    """
    
    if plan_status_list:
        for ps in plan_status_list:
            html += f"""
                        <tr>
                            <td>{ps['plan_name']}</td>
                            <td>{ps['batch_enabled']}</td>
                            <td>{ps['status']}</td>
                        </tr>
            """
    else:
        html += '<tr><td colspan="3" class="empty">有効なプランなし</td></tr>'
    
    html += """
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <div class="section-title error">エラー・警告</div>
                <table>
                    <thead><tr><th>時刻</th><th>レベル</th><th>内容</th></tr></thead>
                    <tbody>
    """
    
    if errors:
        for err in errors:
            time_str = err.created_at.strftime('%H:%M') if err.created_at else '-'
            html += f"""
                        <tr>
                            <td>{time_str}</td>
                            <td>{err.level or 'ERROR'}</td>
                            <td style="max-width:300px;word-break:break-word;">{err.message[:100] if err.message else '-'}</td>
                        </tr>
            """
    else:
        html += '<tr><td colspan="3" class="empty">エラーなし</td></tr>'
    
    html += """
                    </tbody>
                </table>
            </div>
        </div>
        <div class="footer">サッカーご飯メールサービス - 自動送信レポート</div>
    </div>
</body>
</html>
    """
    
    return html


def send_daily_report():
    """日次レポートを管理者全員に送信"""
    db = SessionLocal()
    try:
        today = datetime.now(JST).date()
        
        # 管理者ユーザー取得 (is_admin=True)
        admins = db.query(User).filter(
            User.is_admin == True,
            User.is_active == True,
        ).all()
        
        if not admins:
            logger.warning("日次レポート: 送信先の管理者がいません")
            return {"success": 0, "fail": 0, "message": "管理者がいません"}
        
        # レポートHTML生成
        html_content = generate_daily_report_html(db, today)
        subject = f"サッカーご飯 日次レポート ({today.strftime('%Y-%m-%d')})"
        
        success = 0
        fail = 0
        
        for admin in admins:
            try:
                send_email(
                    to_email=admin.email,
                    subject=subject,
                    body=html_content,
                    is_html=True,
                )
                success += 1
                logger.info(f"日次レポート送信成功: {admin.email}")
            except Exception as e:
                fail += 1
                logger.error(f"日次レポート送信失敗: {admin.email} - {e}")
        
        return {"success": success, "fail": fail}
    
    except Exception as e:
        logger.error(f"日次レポート生成エラー: {e}")
        return {"success": 0, "fail": 0, "error": str(e)}
    finally:
        db.close()
