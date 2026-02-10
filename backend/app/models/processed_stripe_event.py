from sqlalchemy import Column, Integer, String, DateTime, func
from app.core.database import Base


class ProcessedStripeEvent(Base):
    __tablename__ = "processed_stripe_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    processed_at = Column(DateTime, nullable=False, server_default=func.now())
