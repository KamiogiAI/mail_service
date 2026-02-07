"""Resend API メール送信サービス"""
import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from app.core.config import settings
from app.core.api_keys import get_resend_api_key, get_from_email, get_site_name
from app.core.logging import get_logger

logger = get_logger(__name__)

template_dir = Path(__file__).parent.parent / "templates" / "email"
jinja_env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(["html"]),
)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str = None,
    unsubscribe_url: str = None,
    api_key: str = None,
) -> dict:
    """
    HTMLメールをResend APIで送信。
    Returns: {"id": "resend_message_id"} or raises
    """
    resend.api_key = api_key or get_resend_api_key()

    # HTMLテンプレートでラップ
    template = jinja_env.get_template("email_base.html")
    html = template.render(
        body=body,
        unsubscribe_url=unsubscribe_url,
        site_name=get_site_name(),
    )

    result = resend.Emails.send({
        "from": from_email or get_from_email(),
        "to": [to_email],
        "subject": subject,
        "html": html,
    })

    logger.info(f"メール送信成功: to={to_email}, subject={subject[:30]}")
    return result
