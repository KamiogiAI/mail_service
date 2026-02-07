"""管理画面: Firebase認証情報管理"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import encrypt, decrypt
from app.models.firebase_credential import FirebaseCredential
from app.routers.deps import require_admin
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin/firebase-credentials", tags=["admin-firebase"])


class CredentialCreate(BaseModel):
    name: str
    json_content: str  # 平文のサービスアカウントJSON


class CredentialUpdate(BaseModel):
    name: Optional[str] = None
    json_content: Optional[str] = None  # 更新する場合のみ


@router.get("")
async def list_credentials(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Firebase認証情報一覧"""
    credentials = db.query(FirebaseCredential).order_by(FirebaseCredential.name).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in credentials
    ]


@router.post("")
async def create_credential(
    data: CredentialCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Firebase認証情報作成"""
    # 名前の重複チェック
    existing = db.query(FirebaseCredential).filter(FirebaseCredential.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="この名前は既に使用されています")

    # JSONの妥当性チェック
    import json
    try:
        parsed = json.loads(data.json_content)
        if "project_id" not in parsed:
            raise HTTPException(status_code=400, detail="JSONにproject_idが含まれていません")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="無効なJSON形式です")

    credential = FirebaseCredential(
        name=data.name,
        encrypted_json=encrypt(data.json_content),
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)

    return {"id": credential.id, "message": "認証情報を作成しました"}


@router.put("/{credential_id}")
async def update_credential(
    credential_id: int,
    data: CredentialUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Firebase認証情報更新"""
    credential = db.query(FirebaseCredential).filter(FirebaseCredential.id == credential_id).first()
    if not credential:
        raise HTTPException(status_code=404, detail="認証情報が見つかりません")

    if data.name and data.name != credential.name:
        existing = db.query(FirebaseCredential).filter(
            FirebaseCredential.name == data.name,
            FirebaseCredential.id != credential_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="この名前は既に使用されています")
        credential.name = data.name

    if data.json_content:
        import json
        try:
            parsed = json.loads(data.json_content)
            if "project_id" not in parsed:
                raise HTTPException(status_code=400, detail="JSONにproject_idが含まれていません")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="無効なJSON形式です")
        credential.encrypted_json = encrypt(data.json_content)

    db.commit()
    return {"message": "認証情報を更新しました"}


@router.delete("/{credential_id}")
async def delete_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Firebase認証情報削除"""
    credential = db.query(FirebaseCredential).filter(FirebaseCredential.id == credential_id).first()
    if not credential:
        raise HTTPException(status_code=404, detail="認証情報が見つかりません")

    # 使用中のプランがあるかチェック
    from app.models.plan_external_data_setting import PlanExternalDataSetting
    using_plans = db.query(PlanExternalDataSetting).filter(
        PlanExternalDataSetting.firebase_credential_id == credential_id
    ).count()
    if using_plans > 0:
        raise HTTPException(status_code=400, detail=f"この認証情報は{using_plans}件のプランで使用中です")

    db.delete(credential)
    db.commit()
    return {"message": "認証情報を削除しました"}


@router.post("/{credential_id}/test")
async def test_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Firebase認証情報の接続テスト"""
    credential = db.query(FirebaseCredential).filter(FirebaseCredential.id == credential_id).first()
    if not credential:
        raise HTTPException(status_code=404, detail="認証情報が見つかりません")

    try:
        from app.services.firestore_external_service import get_loader_from_credential
        loader = get_loader_from_credential(credential.encrypted_json)
        # 簡単な接続テスト (コレクション一覧取得)
        collections = list(loader.db.collections())
        return {
            "ok": True,
            "project_id": loader.db.project,
            "collections": [c.id for c in collections[:10]],
        }
    except Exception as e:
        logger.error(f"Firebase接続テストエラー: {e}")
        return {"ok": False, "error": str(e)}
