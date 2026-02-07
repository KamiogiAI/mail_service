"""APIキー解決: DB (service_settings) 優先 → 環境変数フォールバック"""
from app.core.database import SessionLocal
from app.core.config import settings
from app.core.security import decrypt
from app.core.logging import get_logger

logger = get_logger(__name__)


def _get_from_db(field_name: str) -> str | None:
    """service_settings テーブルから暗号化キーを取得・復号"""
    db = SessionLocal()
    try:
        from app.models.service_setting import ServiceSetting
        setting = db.query(ServiceSetting).first()
        if not setting:
            return None
        enc_value = getattr(setting, field_name, None)
        if not enc_value:
            return None
        return decrypt(enc_value)
    except Exception as e:
        logger.debug(f"DB APIキー取得スキップ ({field_name}): {e}")
        return None
    finally:
        db.close()


def get_openai_api_key() -> str:
    """OpenAI APIキー: DB優先 → 環境変数"""
    return _get_from_db("openai_api_key_enc") or settings.OPENAI_API_KEY


def get_resend_api_key() -> str:
    """Resend APIキー: DB優先 → 環境変数"""
    return _get_from_db("resend_api_key_enc") or settings.RESEND_API_KEY


def get_stripe_secret_key() -> str:
    """Stripe Secret Key: DB優先 → 環境変数"""
    return _get_from_db("stripe_secret_key_enc") or settings.STRIPE_SECRET_KEY


def get_stripe_webhook_secret() -> str:
    """Stripe Webhook Secret: DB優先 → 環境変数"""
    return _get_from_db("stripe_webhook_secret_enc") or settings.STRIPE_WEBHOOK_SECRET


def get_resend_webhook_secret() -> str:
    """Resend Webhook Secret: DB優先 → 環境変数"""
    return _get_from_db("resend_webhook_secret_enc") or settings.RESEND_WEBHOOK_SECRET


def get_from_email() -> str:
    """送信元メールアドレス: DB優先 → 環境変数"""
    db = SessionLocal()
    try:
        from app.models.service_setting import ServiceSetting
        setting = db.query(ServiceSetting).first()
        if setting and setting.from_email:
            return setting.from_email
    except Exception:
        pass
    finally:
        db.close()
    return settings.RESEND_FROM_EMAIL


def get_site_name() -> str:
    """サイト名: DB優先 → 環境変数"""
    db = SessionLocal()
    try:
        from app.models.service_setting import ServiceSetting
        setting = db.query(ServiceSetting).first()
        if setting and setting.site_name:
            return setting.site_name
    except Exception:
        pass
    finally:
        db.close()
    return settings.SITE_NAME


def get_firebase_credentials() -> dict | None:
    """Firebase SA JSON: DB (service_settings) から復号→dict返却"""
    enc = _get_from_db("firebase_key_json_enc")
    if not enc:
        return None
    try:
        import json
        return json.loads(enc)
    except Exception as e:
        logger.debug(f"Firebase credentials parse失敗: {e}")
        return None


def get_stripe_publishable_key() -> str:
    """Stripe Publishable Key: DB優先 → 環境変数 (非暗号化)"""
    db = SessionLocal()
    try:
        from app.models.service_setting import ServiceSetting
        setting = db.query(ServiceSetting).first()
        if setting and setting.stripe_publishable_key:
            return setting.stripe_publishable_key
    except Exception:
        pass
    finally:
        db.close()
    return settings.STRIPE_PUBLISHABLE_KEY
