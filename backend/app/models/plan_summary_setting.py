from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from app.core.database import Base


class PlanSummarySetting(Base):
    __tablename__ = "plan_summary_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, unique=True)
    summary_prompt = Column(Text, nullable=False, comment="あらすじ生成プロンプト")
    summary_length_target = Column(Integer, nullable=False, default=200, comment="あらすじ目標文字数")
    summary_max_keep = Column(Integer, nullable=False, default=10, comment="保持するあらすじ最大件数")
    summary_inject_count = Column(Integer, nullable=False, default=3, comment="GPT生成時に注入するあらすじ件数")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
