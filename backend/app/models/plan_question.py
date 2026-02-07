from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, Enum as SAEnum, JSON, ForeignKey, func
from app.core.database import Base


class PlanQuestion(Base):
    __tablename__ = "plan_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    var_name = Column(String(100), nullable=False, comment="変数名 (プロンプト内{var_name}に対応)")
    label = Column(String(255), nullable=False, comment="質問ラベル")
    question_type = Column(
        SAEnum("text", "textarea", "number", "date", "select", "radio", "checkbox", "array",
               name="question_type"),
        nullable=False,
        default="text",
    )
    options = Column(JSON, nullable=True, comment="選択肢 (select/radio/checkbox用)")
    array_max = Column(Integer, nullable=True, comment="array型の最大件数")
    array_min = Column(Integer, nullable=True, comment="array型の最低必須件数")
    is_required = Column(Boolean, nullable=False, default=True)
    track_changes = Column(Boolean, nullable=False, default=False, comment="回答変更履歴を記録するか")
    sort_order = Column(Integer, nullable=False, default=0, comment="表示順")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
