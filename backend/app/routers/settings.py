"""サービス設定ルーター"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import encrypt, decrypt
from app.models.service_setting import ServiceSetting
from app.routers.deps import require_admin

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])


class SettingsUpdate(BaseModel):
    site_name: Optional[str] = None
    site_url: Optional[str] = None
    from_email: Optional[str] = None
    openai_api_key: Optional[str] = None
    resend_api_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_publishable_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    resend_webhook_secret: Optional[str] = None
    firebase_key_json: Optional[str] = None
    resend_webhook_enabled: Optional[bool] = None
    allow_multiple_plans: Optional[bool] = None
    terms_md: Optional[str] = None
    company_md: Optional[str] = None
    cancel_md: Optional[str] = None
    tokusho_md: Optional[str] = None
    privacy_md: Optional[str] = None


def _mask(value: str) -> str:
    """APIキーをマスク表示"""
    if not value or len(value) < 8:
        return "****"
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


@router.get("")
async def get_settings(db: Session = Depends(get_db), _=Depends(require_admin)):
    """設定取得"""
    setting = db.query(ServiceSetting).first()
    if not setting:
        # 初期レコード作成
        setting = ServiceSetting()
        db.add(setting)
        db.commit()
        db.refresh(setting)

    # 暗号化キーをマスク表示で返す
    openai_key = ""
    resend_key = ""
    stripe_key = ""
    stripe_wh = ""
    resend_wh = ""

    try:
        if setting.openai_api_key_enc:
            openai_key = _mask(decrypt(setting.openai_api_key_enc))
    except Exception:
        openai_key = "(復号エラー)"

    try:
        if setting.resend_api_key_enc:
            resend_key = _mask(decrypt(setting.resend_api_key_enc))
    except Exception:
        resend_key = "(復号エラー)"

    try:
        if setting.stripe_secret_key_enc:
            stripe_key = _mask(decrypt(setting.stripe_secret_key_enc))
    except Exception:
        stripe_key = "(復号エラー)"

    try:
        if setting.stripe_webhook_secret_enc:
            stripe_wh = _mask(decrypt(setting.stripe_webhook_secret_enc))
    except Exception:
        stripe_wh = "(復号エラー)"

    try:
        if setting.resend_webhook_secret_enc:
            resend_wh = _mask(decrypt(setting.resend_webhook_secret_enc))
    except Exception:
        resend_wh = "(復号エラー)"

    return {
        "site_name": setting.site_name,
        "site_url": setting.site_url,
        "from_email": setting.from_email,
        "openai_api_key_masked": openai_key,
        "resend_api_key_masked": resend_key,
        "stripe_secret_key_masked": stripe_key,
        "stripe_publishable_key": setting.stripe_publishable_key or "",
        "stripe_webhook_secret_masked": stripe_wh,
        "resend_webhook_secret_masked": resend_wh,
        "resend_webhook_enabled": setting.resend_webhook_enabled,
        "allow_multiple_plans": setting.allow_multiple_plans,
        "firebase_client_email": setting.firebase_client_email or "",
        "terms_md": setting.terms_md or "",
        "company_md": setting.company_md or "",
        "cancel_md": setting.cancel_md or "",
        "tokusho_md": setting.tokusho_md or "",
        "privacy_md": setting.privacy_md or "",
    }


@router.put("")
async def update_settings(data: SettingsUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    """設定更新"""
    setting = db.query(ServiceSetting).first()
    if not setting:
        setting = ServiceSetting()
        db.add(setting)

    if data.site_name is not None:
        setting.site_name = data.site_name
    if data.site_url is not None:
        setting.site_url = data.site_url
    if data.from_email is not None:
        setting.from_email = data.from_email

    # APIキーは空文字でなければ暗号化して保存
    if data.openai_api_key:
        setting.openai_api_key_enc = encrypt(data.openai_api_key)
    if data.resend_api_key:
        setting.resend_api_key_enc = encrypt(data.resend_api_key)
    if data.stripe_secret_key:
        setting.stripe_secret_key_enc = encrypt(data.stripe_secret_key)
    if data.stripe_publishable_key is not None:
        setting.stripe_publishable_key = data.stripe_publishable_key
    if data.stripe_webhook_secret:
        setting.stripe_webhook_secret_enc = encrypt(data.stripe_webhook_secret)
    if data.resend_webhook_secret:
        setting.resend_webhook_secret_enc = encrypt(data.resend_webhook_secret)

    # Firebase Key JSON
    if data.firebase_key_json:
        import json
        try:
            parsed = json.loads(data.firebase_key_json)
            client_email = parsed.get("client_email", "")
            setting.firebase_key_json_enc = encrypt(data.firebase_key_json)
            setting.firebase_client_email = client_email
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Firebase Key JSONの形式が不正です")

    if data.resend_webhook_enabled is not None:
        setting.resend_webhook_enabled = data.resend_webhook_enabled
    if data.allow_multiple_plans is not None:
        setting.allow_multiple_plans = data.allow_multiple_plans

    if data.terms_md is not None:
        setting.terms_md = data.terms_md
    if data.company_md is not None:
        setting.company_md = data.company_md
    if data.cancel_md is not None:
        setting.cancel_md = data.cancel_md
    if data.tokusho_md is not None:
        setting.tokusho_md = data.tokusho_md
    if data.privacy_md is not None:
        setting.privacy_md = data.privacy_md

    db.commit()
    return {"message": "設定を更新しました"}
