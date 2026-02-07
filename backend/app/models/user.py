from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SAEnum, func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    member_no = Column(String(8), unique=True, nullable=False, index=True, comment="会員番号 (10000001〜)")
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name_last = Column(String(100), nullable=False, comment="姓")
    name_first = Column(String(100), nullable=False, comment="名")
    role = Column(SAEnum("user", "admin", name="user_role"), nullable=False, default="user")
    email_verified = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    stripe_customer_id = Column(String(255), nullable=True, unique=True)
    trial_used = Column(Boolean, nullable=False, default=False, comment="トライアル使用済み")
    unsubscribe_token = Column(String(64), unique=True, nullable=True, comment="配信停止トークン")
    deliverable = Column(Boolean, nullable=False, default=True, comment="配信可能 (bounce/complaintでfalse)")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
