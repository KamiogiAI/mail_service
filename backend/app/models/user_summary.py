from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, func
from app.core.database import Base


class UserSummary(Base):
    __tablename__ = "user_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_text = Column(Text, nullable=False, comment="あらすじテキスト")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
