"""Resend Webhook ルーター (bounce/complaint → deliverable=false)"""
from fastapi import APIRouter, Request, HTTPException
from svix.webhooks import Webhook, WebhookVerificationError

from app.core.database import SessionLocal
from app.core.api_keys import get_resend_webhook_secret
from app.models.user import User
from app.models.service_setting import ServiceSetting
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/api/webhooks/resend")
async def resend_webhook(request: Request):
    """Resend Webhook エンドポイント (CSRF免除、Svix署名検証)"""
    payload = await request.body()

    # Resend Webhook ON/OFFチェック
    db = SessionLocal()
    try:
        setting = db.query(ServiceSetting).first()
        if not setting or not setting.resend_webhook_enabled:
            return {"received": True, "processed": False, "reason": "webhook_disabled"}

        # 署名検証
        webhook_secret = get_resend_webhook_secret()
        if webhook_secret:
            headers = {
                "svix-id": request.headers.get("svix-id", ""),
                "svix-timestamp": request.headers.get("svix-timestamp", ""),
                "svix-signature": request.headers.get("svix-signature", ""),
            }
            try:
                wh = Webhook(webhook_secret)
                wh.verify(payload, headers)
            except WebhookVerificationError:
                logger.error("Resend webhook署名検証失敗")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # イベント処理
        import json
        data = json.loads(payload)
        event_type = data.get("type", "")

        if event_type in ("email.bounced", "email.complained"):
            _handle_bounce_or_complaint(db, data)
        else:
            logger.info(f"未処理のResendイベント: {event_type}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resend webhook処理エラー: {e}")
    finally:
        db.close()

    return {"received": True}


def _handle_bounce_or_complaint(db, data: dict):
    """bounce/complaint → deliverable=false"""
    event_data = data.get("data", {})
    to_emails = event_data.get("to", [])

    if isinstance(to_emails, str):
        to_emails = [to_emails]

    for email in to_emails:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.deliverable = False
            logger.warning(f"配信停止: email={email}, event={data.get('type')}")

    db.commit()
