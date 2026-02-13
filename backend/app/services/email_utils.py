"""メールアドレス関連ユーティリティ"""
import re
from typing import Optional

# 使い捨てメールドメインのブラックリスト（主要なもの）
DISPOSABLE_DOMAINS = {
    "10minutemail.com", "10minutemail.net", "guerrillamail.com", "guerrillamail.org",
    "tempmail.com", "tempmail.net", "throwaway.email", "mailinator.com",
    "yopmail.com", "yopmail.fr", "trashmail.com", "fakeinbox.com",
    "temp-mail.org", "getnada.com", "mohmal.com", "maildrop.cc",
    "mailnesia.com", "sharklasers.com", "spam4.me", "grr.la",
    "dispostable.com", "mailcatch.com", "tempr.email", "discard.email",
    "tmpmail.org", "tmpmail.net", "emailondeck.com", "mintemail.com",
}


def normalize_email(email: str) -> str:
    """
    メールアドレスを正規化
    - 小文字に変換
    - Gmail/Googlemail: +以降を削除、ドットを削除
    """
    if not email:
        return email
    
    email = email.lower().strip()
    
    local, domain = email.rsplit("@", 1)
    
    # Gmail / Googlemail の正規化
    if domain in ("gmail.com", "googlemail.com"):
        # +以降を削除
        if "+" in local:
            local = local.split("+")[0]
        # ドットを削除
        local = local.replace(".", "")
        # googlemail.com → gmail.com に統一
        domain = "gmail.com"
    
    return f"{local}@{domain}"


def is_disposable_email(email: str) -> bool:
    """使い捨てメールアドレスかどうかをチェック"""
    if not email:
        return False
    
    domain = email.lower().split("@")[-1]
    return domain in DISPOSABLE_DOMAINS


def validate_email_for_registration(email: str) -> Optional[str]:
    """
    登録用メールアドレスのバリデーション
    エラーがあればエラーメッセージを返す、問題なければNone
    """
    if is_disposable_email(email):
        return "使い捨てメールアドレスは使用できません"
    
    return None
