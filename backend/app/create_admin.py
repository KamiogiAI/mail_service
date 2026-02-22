"""初期管理者アカウント作成スクリプト

使用方法:
    # 環境変数でパスワードを指定（推奨）
    ADMIN_PASSWORD=強いパスワード python -m app.create_admin
    
    # 自動生成（パスワードは1度だけ画面に表示されます）
    python -m app.create_admin
"""
import os
import secrets
from app.core.database import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password, generate_member_no, generate_unsubscribe_token

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")


def _generate_secure_password() -> str:
    """セキュアなランダムパスワードを生成（16文字）"""
    return secrets.token_urlsafe(16)


def main():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing:
            print(f"既に存在します: {ADMIN_EMAIL}")
            return

        # 環境変数からパスワードを取得、なければ自動生成
        password = os.environ.get("ADMIN_PASSWORD")
        if not password:
            password = _generate_secure_password()
            print("=" * 60)
            print("⚠️  パスワードは自動生成されました")
            print("⚠️  以下のパスワードは一度しか表示されません。安全に保管してください。")
            print("=" * 60)
            print(f"パスワード: {password}")
            print("=" * 60)
        
        user = User(
            member_no=generate_member_no(db),
            email=ADMIN_EMAIL,
            password_hash=hash_password(password),
            name_last="管理者",
            name_first="",
            role="admin",
            email_verified=True,
            is_active=True,
            unsubscribe_token=generate_unsubscribe_token(),
            deliverable=True,
        )
        db.add(user)
        db.commit()
        # セキュリティ: パスワードはログに出力しない
        print(f"管理者作成完了: email={ADMIN_EMAIL}")
        print("⚠️  初回ログイン後、必ずパスワードを変更してください。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
