"""静的ページAPI (利用規約等)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.service_setting import ServiceSetting

router = APIRouter(prefix="/api/pages", tags=["pages"])

@router.get("")
async def get_site_info(db: Session = Depends(get_db)):
    """サイト基本情報 (認証不要)"""
    setting = db.query(ServiceSetting).first()
    return {
        "site_name": setting.site_name if setting else "Mail Service",
    }


PAGE_FIELDS = {
    "terms": "terms_md",
    "company": "company_md",
    "cancel": "cancel_md",
    "tokusho": "tokusho_md",
    "privacy": "privacy_md",
}

PAGE_TITLES = {
    "terms": "利用規約",
    "company": "運営会社情報",
    "cancel": "解約ポリシー",
    "tokusho": "特定商取引法に基づく表記",
    "privacy": "プライバシーポリシー",
}


@router.get("/{page_type}")
async def get_page(page_type: str, db: Session = Depends(get_db)):
    """静的ページ内容取得"""
    field = PAGE_FIELDS.get(page_type)
    if not field:
        raise HTTPException(status_code=404, detail="ページタイプが不正です")

    setting = db.query(ServiceSetting).first()
    content = getattr(setting, field, "") if setting else ""

    return {
        "type": page_type,
        "title": PAGE_TITLES.get(page_type, ""),
        "content_md": content or "",
    }
