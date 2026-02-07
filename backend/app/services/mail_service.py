"""トランザクションメール送信 (認証コード、パスワードリセット等)"""
import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from app.core.config import settings
from app.core.api_keys import get_resend_api_key, get_from_email, get_site_name
from app.core.logging import get_logger

logger = get_logger(__name__)

# テンプレートエンジン
template_dir = Path(__file__).parent.parent / "templates" / "email"
jinja_env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(["html"]),
)


def _get_resend_api_key() -> str:
    """Resend APIキーを取得 (DB優先 → 環境変数フォールバック)"""
    return get_resend_api_key()


def send_verify_code_email(to_email: str, name: str, code: str) -> bool:
    """メール認証コード送信"""
    try:
        resend.api_key = _get_resend_api_key()
        template = jinja_env.get_template("verify_code.html")
        html = template.render(name=name, code=code, site_name=get_site_name())

        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】メール認証コード",
            "html": html,
        })
        logger.info(f"認証コードメール送信: {to_email}")
        return True
    except Exception as e:
        logger.error(f"認証コードメール送信失敗: {to_email} - {e}")
        return False


def send_password_change_code_email(to_email: str, name: str, code: str) -> bool:
    """パスワード変更用認証コード送信"""
    try:
        resend.api_key = _get_resend_api_key()
        template = jinja_env.get_template("password_change_code.html")
        html = template.render(name=name, code=code, site_name=get_site_name())

        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】パスワード変更認証コード",
            "html": html,
        })
        logger.info(f"パスワード変更認証コードメール送信: {to_email}")
        return True
    except Exception as e:
        logger.error(f"パスワード変更認証コードメール送信失敗: {to_email} - {e}")
        return False


def send_password_reset_email(to_email: str, name: str, reset_url: str) -> bool:
    """パスワードリセットメール送信"""
    try:
        resend.api_key = _get_resend_api_key()
        template = jinja_env.get_template("password_reset.html")
        html = template.render(name=name, reset_url=reset_url, site_name=get_site_name())

        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】パスワードリセット",
            "html": html,
        })
        logger.info(f"パスワードリセットメール送信: {to_email}")
        return True
    except Exception as e:
        logger.error(f"パスワードリセットメール送信失敗: {to_email} - {e}")
        return False


def send_subscription_cancel_email(to_email: str, name: str, plan_name: str) -> bool:
    """プラン強制解約通知メール"""
    try:
        resend.api_key = _get_resend_api_key()
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>{get_site_name()}</h2>
            <p>{name} 様</p>
            <p>ご利用いただいていた「{plan_name}」プランが終了いたしました。</p>
            <p>引き続きサービスをご利用される場合は、新しいプランへの加入をお願いいたします。</p>
            <p><a href="{settings.SITE_URL}">プラン一覧を見る</a></p>
        </div>
        """
        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】プラン終了のお知らせ",
            "html": html,
        })
        return True
    except Exception as e:
        logger.error(f"解約通知メール送信失敗: {to_email} - {e}")
        return False


def send_payment_failed_email(to_email: str, name: str, plan_name: str) -> bool:
    """決済失敗通知メール"""
    try:
        resend.api_key = _get_resend_api_key()
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>{get_site_name()}</h2>
            <p>{name} 様</p>
            <p>「{plan_name}」プランの決済に失敗しました。配信を一時停止しております。</p>
            <p>お支払い方法をご確認のうえ、更新をお願いいたします。</p>
            <p><a href="{settings.SITE_URL}/user/mypage.html">マイページで確認する</a></p>
        </div>
        """
        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】決済失敗のお知らせ",
            "html": html,
        })
        return True
    except Exception as e:
        logger.error(f"決済失敗通知メール送信失敗: {to_email} - {e}")
        return False
