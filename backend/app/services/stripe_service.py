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


# Billing Portal Configuration IDのキャッシュ
_portal_config_cache = {
    "trial": None,      # トライアル用（プラン変更無効）
    "normal": None,     # 通常用（プラン変更有効、日割りあり）
}


def _get_or_create_portal_configurations() -> dict:
    """Billing Portal Configuration を取得または作成（トライアル用/通常用の2種類）
    
    Returns:
        {"trial": config_id, "normal": config_id}
    """
    global _portal_config_cache
    _init_stripe()
    
    # キャッシュがあればそれを返す
    if _portal_config_cache["trial"] and _portal_config_cache["normal"]:
        return _portal_config_cache
    
    # 共通設定
    base_features = {
        "subscription_cancel": {
            "enabled": True,
            "mode": "at_period_end",
        },
        "payment_method_update": {"enabled": True},
        "invoice_history": {"enabled": True},
    }
    
    # 既存のConfigurationを取得
    configs = stripe.billing_portal.Configuration.list(limit=10)
    
    trial_config_id = None
    normal_config_id = None
    
    for config in configs.data:
        sub_update = config.features.subscription_update
        headline = getattr(config.business_profile, 'headline', '') if config.business_profile else ''
        
        if headline == "プランの管理（トライアル中）":
            trial_config_id = config.id
        elif headline == "プランの管理":
            # プラン変更が有効で日割りありなら通常用
            if sub_update.enabled and getattr(sub_update, 'proration_behavior', None) == "create_prorations":
                normal_config_id = config.id
    
    # トライアル用がなければ作成
    if not trial_config_id:
        trial_features = {
            **base_features,
            "subscription_update": {"enabled": False},
        }
        config = stripe.billing_portal.Configuration.create(
            features=trial_features,
            business_profile={"headline": "プランの管理（トライアル中）"},
        )
        trial_config_id = config.id
        logger.info(f"Billing Portal Configuration作成（トライアル用）: {config.id}")
    
    # 通常用がなければ作成（初期はプラン変更無効、update_billing_portal_productsで有効化）
    if not normal_config_id:
        normal_features = {
            **base_features,
            "subscription_update": {"enabled": False},  # productsが必須なので初期は無効
        }
        config = stripe.billing_portal.Configuration.create(
            features=normal_features,
            business_profile={"headline": "プランの管理"},
        )
        normal_config_id = config.id
        logger.info(f"Billing Portal Configuration作成（通常用、初期状態）: {config.id}")
    
    _portal_config_cache["trial"] = trial_config_id
    _portal_config_cache["normal"] = normal_config_id
    
    return _portal_config_cache


def create_billing_portal_session(customer_id: str, return_url: str, is_trial: bool = False) -> str:
    """Billing Portal Session を作成し URL を返す
    
    Args:
        customer_id: Stripe Customer ID
        return_url: ポータルから戻るURL
        is_trial: トライアル中かどうか（Trueならプラン変更無効）
    """
    _init_stripe()
    
    configs = _get_or_create_portal_configurations()
    config_id = configs["trial"] if is_trial else configs["normal"]
    
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
        configuration=config_id,
    )
    
    logger.info(f"Billing Portal Session作成: customer={customer_id}, is_trial={is_trial}")
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
    applies_to_products: list[str] = None,
) -> str:
    """Stripe Coupon 作成
    
    Args:
        applies_to_products: 対象プロダクトIDのリスト (指定すると対象外プロダクトにはクーポン適用不可)
    """
    _init_stripe()
    params = {"duration": duration, "name": name or f"Discount {discount_value}"}
    if discount_type == "percent_off":
        params["percent_off"] = discount_value
    else:
        params["amount_off"] = discount_value
        params["currency"] = "jpy"
    
    # 対象プロダクト制限
    if applies_to_products:
        params["applies_to"] = {"products": applies_to_products}
    
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


def remove_subscription_coupon(subscription_id: str) -> bool:
    """Stripeのsubscriptionからクーポン/割引を削除
    
    Returns:
        bool: 成功したらTrue
    """
    _init_stripe()
    try:
        stripe.Subscription.modify(subscription_id, coupon="")
        return True
    except Exception:
        return False


def get_subscription_discount_info(subscription_id: str) -> dict:
    """Stripeのsubscriptionから割引情報を取得
    
    Returns:
        dict: {
            "stripe_coupon_id": StripeのクーポンID or None,
            "discount_name": クーポン名 or None,
            "discount_percent": 割引率(%) or None,
            "discount_amount": 割引額(円) or None,
        }
    """
    _init_stripe()
    try:
        sub = stripe.Subscription.retrieve(subscription_id, expand=["discount.coupon"])
        
        discount = sub.get("discount")
        if not discount:
            return {"stripe_coupon_id": None, "discount_name": None, "discount_percent": None, "discount_amount": None}
        
        coupon = discount.get("coupon", {})
        stripe_coupon_id = coupon.get("id")
        discount_name = coupon.get("name") or coupon.get("id")
        discount_percent = coupon.get("percent_off")  # 例: 10.0 (10%)
        discount_amount = coupon.get("amount_off")  # 単位: 通貨の最小単位 (円なら円)
        
        return {
            "stripe_coupon_id": stripe_coupon_id,
            "discount_name": discount_name,
            "discount_percent": discount_percent,
            "discount_amount": discount_amount,
        }
    except Exception:
        return {"stripe_coupon_id": None, "discount_name": None, "discount_percent": None, "discount_amount": None}


def construct_webhook_event(payload: bytes, sig_header: str, secret: str):
    """Webhook イベントを構築・検証"""
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def update_billing_portal_products(products: list[dict]) -> bool:
    """Billing Portal Configuration（通常用）のプラン変更可能プロダクトを更新
    
    Args:
        products: [{"product": "prod_xxx", "prices": ["price_yyy"]}, ...]
    
    Returns:
        bool: 成功したらTrue
    """
    _init_stripe()
    
    try:
        # 通常用Configurationを取得または作成
        configs = _get_or_create_portal_configurations()
        normal_config_id = configs["normal"]
        
        # productsがある場合のみプラン変更を有効化
        if products:
            subscription_update = {
                "enabled": True,
                "default_allowed_updates": ["price", "promotion_code"],
                "proration_behavior": "create_prorations",
                "products": products,
            }
        else:
            subscription_update = {"enabled": False}
        
        features = {
            "subscription_update": subscription_update,
            "subscription_cancel": {
                "enabled": True,
                "mode": "at_period_end",
            },
            "payment_method_update": {"enabled": True},
            "invoice_history": {"enabled": True},
        }
        
        stripe.billing_portal.Configuration.modify(normal_config_id, features=features)
        logger.info(f"Billing Portal products更新（通常用）: {len(products)}プラン, enabled={bool(products)}")
        
        return True
    except Exception as e:
        logger.error(f"Billing Portal products更新失敗: {e}")
        return False
