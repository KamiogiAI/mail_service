from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, func
from app.core.database import Base


class PlanExternalDataSetting(Base):
    __tablename__ = "plan_external_data_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, unique=True)
    external_data_path = Column(String(500), nullable=False, comment="Firestoreパス (collection/doc または collection/doc/~)")
    firebase_credential_id = Column(Integer, ForeignKey("firebase_credentials.id", ondelete="SET NULL"), nullable=True, comment="Firebase認証情報ID")
    delete_after_process = Column(Boolean, nullable=False, default=False, comment="処理後にFirestoreデータを削除")
    # 後方互換: 既存データ用
    firebase_key_json_enc = Column(Text, nullable=True, comment="[非推奨] Firebase Service Account JSON (暗号化)")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
