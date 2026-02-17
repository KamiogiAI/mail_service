"""Stripe Invoice 記録モデル"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.core.database import Base


class InvoiceRecord(Base):
    """Stripe Invoiceの支払い記録"""
    __tablename__ = "invoice_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stripe_invoice_id = Column(String(255), unique=True, nullable=False, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # 金額（円）
    amount_paid = Column(Integer, nullable=False, comment="実際の支払額（円）")
    subtotal = Column(Integer, nullable=True, comment="小計（割引前）")
    discount_amount = Column(Integer, nullable=True, comment="割引額")
    
    # プロモーション情報
    promotion_code_id = Column(Integer, ForeignKey("promotion_codes.id", ondelete="SET NULL"), nullable=True)
    coupon_id = Column(String(255), nullable=True, comment="Stripe Coupon ID")
    
    # 期間
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    
    # ステータス
    status = Column(String(50), nullable=False, default="paid", comment="paid/void/uncollectible")
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
