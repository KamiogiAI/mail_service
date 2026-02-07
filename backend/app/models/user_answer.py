from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, UniqueConstraint, func
from app.core.database import Base


class UserAnswer(Base):
    __tablename__ = "user_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("plan_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    answer_value = Column(Text, nullable=True, comment="回答値 (JSON文字列の場合あり)")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_user_question"),
    )
