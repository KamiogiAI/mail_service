"""Stripe API操作サービス"""
import stripe
from typing import Optional
from app.core.api_keys import get_stripe_secret_key
from app.core.logging import get_logger

logger = get_logger(__name__)


def _init_stripe():
    stripe.api_key = get_stripe_secret_key()


def create_product_and_price(name: str, description: str, price_yen: int) -> tuple[str, str]:
    """Stripe Product と Price を作成"""
    _init_stripe()
    product = stripe.Product.create(
        name=name,
        description=description or name,
    )
    price = stripe.Price.create(
        product=product.id,
        unit_amount=price_yen,
        currency="jpy",
        recurring={"interval": "month"},
    )
    logger.info(f"Stripe Product/Price作成: product={product.id}, price={price.id}")
    return product.id, price.id


def update_product(product_id: str, name: str, description: str):
    """Stripe Product 更新"""
    _init_stripe()
    stripe.Product.modify(product_id, name=name, description=description or name)


def archive_product(product_id: str):
    """Stripe Product をアーカイブ"""
    _init_stripe()
    stripe.Product.modify(product_id, active=False)


def create_checkout_session(
    price_id: str,
    customer_id: Optional[str],
    customer_email: Optional[str],
    trial_days: Optional[int],
    success_url: str,
    cancel_url: str,
    metadata: dict = None,
    stripe_promotion_code_id: Optional[str] = None,
) -> str:
    """Checkout Session を作成し URL を返す"""
    _init_stripe()
    params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if stripe_promotion_code_id:
        params["discounts"] = [{"promotion_code": stripe_promotion_code_id}]
    else:
        params["allow_promotion_codes"] = False

    if customer_id:
        params["customer"] = customer_id
    elif customer_email:
        params["customer_email"] = customer_email

    if trial_days and trial_days > 0:
        params["subscription_data"] = {"trial_period_days": trial_days}

    if metadata:
        params["metadata"] = metadata

    session = stripe.checkout.Session.create(**params)
    return session.url


def create_customer(email: str, name: str, metadata: dict = None) -> str:
    """Stripe Customer 作成"""
    _init_stripe()
    customer = stripe.Customer.create(
        email=email,
        name=name,
        metadata=metadata or {},
    )
    return customer.id


def create_billing_portal_session(customer_id: str, return_url: str) -> str:
    """Billing Portal Session を作成し URL を返す"""
    _init_stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


def cancel_subscription(subscription_id: str, at_period_end: bool = True):
    """購読をキャンセル"""
    _init_stripe()
    if at_period_end:
        stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
    else:
        stripe.Subscription.cancel(subscription_id)


def cancel_subscription_immediately(subscription_id: str):
    """購読を即時キャンセル"""
    _init_stripe()
    stripe.Subscription.cancel(subscription_id)


def create_coupon(
    discount_type: str,
    discount_value: int,
    duration: str = "forever",
    name: str = "",
) -> str:
    """Stripe Coupon 作成"""
    _init_stripe()
    params = {"duration": duration, "name": name or f"Discount {discount_value}"}
    if discount_type == "percent_off":
        params["percent_off"] = discount_value
    else:
        params["amount_off"] = discount_value
        params["currency"] = "jpy"
    coupon = stripe.Coupon.create(**params)
    return coupon.id


def create_promotion_code(
    coupon_id: str,
    code: str,
    max_redemptions: Optional[int] = None,
    expires_at: Optional[int] = None,
) -> str:
    """Stripe Promotion Code 作成"""
    _init_stripe()
    params = {"coupon": coupon_id, "code": code}
    if max_redemptions:
        params["max_redemptions"] = max_redemptions
    if expires_at:
        params["expires_at"] = expires_at
    promo = stripe.PromotionCode.create(**params)
    return promo.id


def deactivate_promotion_code(promotion_code_id: str):
    """Promotion Code を無効化"""
    _init_stripe()
    stripe.PromotionCode.modify(promotion_code_id, active=False)


def retrieve_checkout_session(session_id: str):
    """Checkout Session を取得"""
    _init_stripe()
    return stripe.checkout.Session.retrieve(session_id, expand=["subscription"])


def retrieve_subscription(subscription_id: str) -> dict:
    """Stripe Subscription を取得"""
    _init_stripe()
    return stripe.Subscription.retrieve(subscription_id)


def construct_webhook_event(payload: bytes, sig_header: str, secret: str):
    """Webhook イベントを構築・検証"""
    return stripe.Webhook.construct_event(payload, sig_header, secret)
