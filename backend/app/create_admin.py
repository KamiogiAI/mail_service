"""初期管理者アカウント作成スクリプト"""
from app.core.database import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password, generate_member_no, generate_unsubscribe_token

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"


def main():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing:
            print(f"既に存在します: {ADMIN_EMAIL}")
            return

        user = User(
            member_no=generate_member_no(db),
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
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
        print(f"管理者作成完了: email={ADMIN_EMAIL}, password={ADMIN_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
