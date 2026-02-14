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


def send_welcome_email(to_email: str, name: str) -> bool:
    """登録完了ウェルカムメール送信"""
    try:
        resend.api_key = _get_resend_api_key()
        template = jinja_env.get_template("welcome.html")
        html = template.render(
            name=name,
            site_name=get_site_name(),
            site_url=settings.SITE_URL,
        )

        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": "あなた専用の成長設計を準備しています",
            "html": html,
        })
        logger.info(f"ウェルカムメール送信: {to_email}")
        return True
    except Exception as e:
        logger.error(f"ウェルカムメール送信失敗: {to_email} - {e}")
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


def send_admin_invite_email(to_email: str, name: str, temp_password: str) -> bool:
    """管理者招待メール送信（仮パスワード通知）"""
    try:
        resend.api_key = _get_resend_api_key()
        login_url = f"{settings.SITE_URL}/admin/login.html"
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>{get_site_name()} 管理画面</h2>
            <p>{name} 様</p>
            <p>管理者として招待されました。以下の仮パスワードでログインしてください。</p>
            <div style="background: #f5f5f5; padding: 15px; margin: 20px 0; border-radius: 5px;">
                <p style="margin: 5px 0;"><strong>メールアドレス:</strong> {to_email}</p>
                <p style="margin: 5px 0;"><strong>仮パスワード:</strong> <code style="background: #fff; padding: 2px 8px;">{temp_password}</code></p>
            </div>
            <p style="color: #d93025;"><strong>⚠️ 初回ログイン後、必ずパスワードを変更してください。</strong></p>
            <p><a href="{login_url}" style="display: inline-block; background: #4285f4; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;">管理画面にログイン</a></p>
        </div>
        """
        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】管理者招待のお知らせ",
            "html": html,
        })
        logger.info(f"管理者招待メール送信: {to_email}")
        return True
    except Exception as e:
        logger.error(f"管理者招待メール送信失敗: {to_email} - {e}")
        return False


# =========================================================
# 購読関連メール
# =========================================================

def send_subscription_welcome_email(
    to_email: str,
    name: str,
    plan_name: str,
    plan_price: int,
    next_billing_date: str,
    is_trial: bool = False,
    trial_end_date: str = None,
) -> bool:
    """加入完了メール"""
    try:
        resend.api_key = _get_resend_api_key()
        
        trial_notice = ""
        if is_trial and trial_end_date:
            trial_notice = f"""
            <div style="background: #fff3cd; padding: 15px; margin: 20px 0; border-radius: 5px; border-left: 4px solid #ffc107;">
                <p style="margin: 0; color: #856404;"><strong>🎁 初月無料トライアル中</strong></p>
                <p style="margin: 10px 0 0 0; color: #856404;">
                    トライアル期間: <strong>{trial_end_date}</strong> まで<br>
                    期間中に解約されない場合、自動的に有料プランへ移行し、月額 <strong>¥{plan_price:,}</strong> が請求されます。
                </p>
            </div>
            """
        
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #28a745;">🎉 ご加入ありがとうございます！</h2>
            <p>{name} 様</p>
            <p>「<strong>{plan_name}</strong>」プランへのご加入が完了しました。</p>
            
            <div style="background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 5px;">
                <p style="margin: 5px 0;"><strong>プラン名:</strong> {plan_name}</p>
                <p style="margin: 5px 0;"><strong>月額料金:</strong> ¥{plan_price:,}</p>
                <p style="margin: 5px 0;"><strong>次回更新日:</strong> {next_billing_date}</p>
            </div>
            
            {trial_notice}
            
            <p>マイページからいつでもプラン変更・解約が可能です。</p>
            <p><a href="{settings.SITE_URL}/user/mypage.html" style="display: inline-block; background: #28a745; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;">マイページを見る</a></p>
        </div>
        """
        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】ご加入ありがとうございます",
            "html": html,
        })
        logger.info(f"加入完了メール送信: {to_email}, plan={plan_name}")
        return True
    except Exception as e:
        logger.error(f"加入完了メール送信失敗: {to_email} - {e}")
        return False


def send_plan_change_email(
    to_email: str,
    name: str,
    old_plan_name: str,
    new_plan_name: str,
    new_plan_price: int,
    change_date: str,
    is_immediate: bool = True,
) -> bool:
    """プラン変更通知メール"""
    try:
        resend.api_key = _get_resend_api_key()
        
        if is_immediate:
            timing_text = "本日より"
            notice = "日割り計算により、差額が請求または返金されます。"
        else:
            timing_text = f"{change_date} より"
            notice = "現在のプランは期間終了まで引き続きご利用いただけます。"
        
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>📋 プラン変更のお知らせ</h2>
            <p>{name} 様</p>
            <p>プランの変更が完了しました。</p>
            
            <div style="background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 5px;">
                <p style="margin: 5px 0;"><strong>変更前:</strong> {old_plan_name}</p>
                <p style="margin: 5px 0;"><strong>変更後:</strong> {new_plan_name} (月額 ¥{new_plan_price:,})</p>
                <p style="margin: 5px 0;"><strong>適用日:</strong> {timing_text}</p>
            </div>
            
            <p style="color: #666;">{notice}</p>
            
            <p><a href="{settings.SITE_URL}/user/mypage.html" style="display: inline-block; background: #4285f4; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;">マイページで確認</a></p>
        </div>
        """
        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】プラン変更完了のお知らせ",
            "html": html,
        })
        logger.info(f"プラン変更メール送信: {to_email}, {old_plan_name} → {new_plan_name}")
        return True
    except Exception as e:
        logger.error(f"プラン変更メール送信失敗: {to_email} - {e}")
        return False


def send_cancel_scheduled_email(
    to_email: str,
    name: str,
    plan_name: str,
    end_date: str,
) -> bool:
    """解約予約完了メール"""
    try:
        resend.api_key = _get_resend_api_key()
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>📝 解約予約を受け付けました</h2>
            <p>{name} 様</p>
            <p>「<strong>{plan_name}</strong>」プランの解約予約を承りました。</p>
            
            <div style="background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 5px;">
                <p style="margin: 5px 0;"><strong>プラン名:</strong> {plan_name}</p>
                <p style="margin: 5px 0;"><strong>終了日:</strong> {end_date}</p>
            </div>
            
            <p><strong>{end_date}</strong> まで引き続きサービスをご利用いただけます。</p>
            <p>解約を取り消す場合は、マイページから再開手続きが可能です。</p>
            
            <p><a href="{settings.SITE_URL}/user/mypage.html" style="display: inline-block; background: #6c757d; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;">マイページで確認</a></p>
            
            <p style="color: #666; font-size: 14px; margin-top: 30px;">
                ご利用いただきありがとうございました。<br>
                またのご利用をお待ちしております。
            </p>
        </div>
        """
        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】解約予約完了のお知らせ",
            "html": html,
        })
        logger.info(f"解約予約メール送信: {to_email}, plan={plan_name}")
        return True
    except Exception as e:
        logger.error(f"解約予約メール送信失敗: {to_email} - {e}")
        return False


def send_trial_ending_email(
    to_email: str,
    name: str,
    plan_name: str,
    plan_price: int,
    trial_end_date: str,
) -> bool:
    """トライアル終了間近メール（3日前）"""
    try:
        resend.api_key = _get_resend_api_key()
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #ffc107;">⏰ トライアル終了のお知らせ</h2>
            <p>{name} 様</p>
            <p>「<strong>{plan_name}</strong>」プランの無料トライアル期間がまもなく終了します。</p>
            
            <div style="background: #fff3cd; padding: 20px; margin: 20px 0; border-radius: 5px; border-left: 4px solid #ffc107;">
                <p style="margin: 5px 0;"><strong>トライアル終了日:</strong> {trial_end_date}</p>
                <p style="margin: 5px 0;"><strong>継続時の月額料金:</strong> ¥{plan_price:,}</p>
            </div>
            
            <p><strong>継続する場合:</strong><br>
            特に手続きは不要です。トライアル終了後、自動的に有料プランへ移行します。</p>
            
            <p><strong>解約する場合:</strong><br>
            トライアル期間中にマイページから解約手続きを行ってください。</p>
            
            <p><a href="{settings.SITE_URL}/user/mypage.html" style="display: inline-block; background: #ffc107; color: #000; padding: 10px 20px; text-decoration: none; border-radius: 5px;">マイページで確認</a></p>
        </div>
        """
        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】トライアル終了まであと3日です",
            "html": html,
        })
        logger.info(f"トライアル終了間近メール送信: {to_email}, plan={plan_name}")
        return True
    except Exception as e:
        logger.error(f"トライアル終了間近メール送信失敗: {to_email} - {e}")
        return False


def send_renewal_complete_email(
    to_email: str,
    name: str,
    plan_name: str,
    amount: int,
    next_billing_date: str,
) -> bool:
    """更新完了メール（毎月の請求成功時）"""
    try:
        resend.api_key = _get_resend_api_key()
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #28a745;">✅ 更新完了のお知らせ</h2>
            <p>{name} 様</p>
            <p>「<strong>{plan_name}</strong>」プランの更新が完了しました。</p>
            
            <div style="background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 5px;">
                <p style="margin: 5px 0;"><strong>プラン名:</strong> {plan_name}</p>
                <p style="margin: 5px 0;"><strong>今回のお支払い:</strong> ¥{amount:,}</p>
                <p style="margin: 5px 0;"><strong>次回更新日:</strong> {next_billing_date}</p>
            </div>
            
            <p>引き続きサービスをお楽しみください。</p>
            
            <p><a href="{settings.SITE_URL}/user/mypage.html" style="display: inline-block; background: #28a745; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;">マイページを見る</a></p>
        </div>
        """
        resend.Emails.send({
            "from": get_from_email(),
            "to": [to_email],
            "subject": f"【{get_site_name()}】更新完了のお知らせ",
            "html": html,
        })
        logger.info(f"更新完了メール送信: {to_email}, plan={plan_name}, amount={amount}")
        return True
    except Exception as e:
        logger.error(f"更新完了メール送信失敗: {to_email} - {e}")
        return False
