from sqlalchemy import Column, Integer, String, Date, SmallInteger, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint, Text, func
from app.core.database import Base


class ProgressPlan(Base):
    """
    プラン配信の進捗管理テーブル

    status:
        0 = PENDING (未実行)
        1 = RUNNING (実行中)
        2 = COMPLETE (完了)
        3 = ERROR (エラー)

    heartbeat_at:
        Watchdog用。Workerが処理中に定期的に更新する。
        古いheartbeatはプロセス死亡と判断してリトライ対象。

    cursor:
        途中再開用。最後に処理したdelivery_item_idを保存。
        障害復旧時にここから再開可能。
    """
    __tablename__ = "progress_plan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, comment="配信日 (JST)")
    send_type = Column(
        SAEnum("scheduled", "manual", name="progress_send_type"),
        nullable=False,
    )
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="SET NULL"), nullable=True)
    status = Column(SmallInteger, nullable=False, default=0, comment="0=未実行, 1=実行中, 2=完了, 3=エラー")

    # Watchdog用: 処理中に定期更新されるハートビート
    heartbeat_at = Column(DateTime, nullable=True)
    # リトライ管理
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    # 途中再開用: 最後に処理したアイテムID
    cursor = Column(String(255), nullable=True)
    # エラー情報
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("plan_id", "date", "send_type", "delivery_id", name="uq_plan_date_type_delivery"),
    )
