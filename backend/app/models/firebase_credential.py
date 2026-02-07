"""Firebase認証情報"""
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base


class FirebaseCredential(Base):
    __tablename__ = "firebase_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, comment="認証情報の識別名")
    encrypted_json = Column(Text, nullable=False, comment="暗号化されたサービスアカウントJSON")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
