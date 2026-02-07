from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from app.core.database import Base


class UserAnswerHistory(Base):
    __tablename__ = "user_answer_histories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("plan_questions.id", ondelete="SET NULL"), nullable=True)
    var_name = Column(String(100), nullable=False, comment="変数名スナップショット")
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_at = Column(DateTime, nullable=False, server_default=func.now())
