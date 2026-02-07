"""Firebase/Firestore 外部データ読み込みサービス

仕様:
- シングルモード (collection/document): 1ドキュメント + サブコレクションを取得
- スプリットモード (collection/document/~): サブコレクション/ドキュメントごとに個別処理

返却構造:
{
    "doc": { フィールド },
    "subcollections": {
        "subcol_name": {
            "doc_id_1": { ... },
            "doc_id_2": { ... }
        }
    }
}
"""
import json
from typing import Optional
from google.cloud import firestore
from google.oauth2 import service_account
from app.core.security import decrypt
from app.core.logging import get_logger

logger = get_logger(__name__)


class ExternalDataLoader:
    """Firestore外部データローダー"""

    def __init__(self, credential_json: str):
        """
        Args:
            credential_json: サービスアカウントJSON (平文)
        """
        key_dict = json.loads(credential_json)
        creds = service_account.Credentials.from_service_account_info(key_dict)
        self.db = firestore.Client(credentials=creds, project=key_dict.get("project_id"))

    def load_data(self, collection: str, document: str) -> dict:
        """
        ドキュメントとサブコレクションを読み込む

        Returns:
            {
                "doc": { フィールド },
                "subcollections": { サブコレクション名: { doc_id: { ... } } }
            }
        """
        doc_ref = self.db.collection(collection).document(document)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Firestoreドキュメントが見つかりません: {collection}/{document}")
            return {"doc": {}, "subcollections": {}}

        # ドキュメントフィールド
        doc_data = _serialize(doc.to_dict())

        # サブコレクション
        subcollections = {}
        for subcol in doc_ref.collections():
            subcol_data = {}
            for subdoc in subcol.stream():
                subcol_data[subdoc.id] = _serialize(subdoc.to_dict())
            subcollections[subcol.id] = subcol_data

        return {"doc": doc_data, "subcollections": subcollections}

    def list_subcollection_or_documents(self, path: str) -> list[tuple[str, str, str]]:
        """
        スプリット対象の一覧を取得

        Args:
            path: ベースパス (末尾の/~は除去済み)
                  - "collection" → ドキュメント一覧
                  - "collection/document" → サブコレクション内ドキュメント一覧

        Returns:
            [(item_name, collection_path, document_id), ...]
        """
        parts = path.strip("/").split("/")

        if len(parts) == 1:
            # collection/~ → コレクション内のドキュメント一覧
            collection = parts[0]
            docs = self.db.collection(collection).stream()
            return [(doc.id, collection, doc.id) for doc in docs]

        elif len(parts) == 2:
            # collection/document/~ → サブコレクション内のドキュメント一覧
            collection, document = parts
            doc_ref = self.db.collection(collection).document(document)
            items = []
            for subcol in doc_ref.collections():
                for subdoc in subcol.stream():
                    # item_name はサブコレクション名/ドキュメントID
                    items.append((subdoc.id, f"{collection}/{document}/{subcol.id}", subdoc.id))
            return items

        else:
            # より深いパス (collection/doc/subcol/doc/~)
            ref = self.db
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    ref = ref.collection(part)
                else:
                    ref = ref.document(part)

            items = []
            if hasattr(ref, 'collections'):
                # ドキュメントの場合 → サブコレクション列挙
                for subcol in ref.collections():
                    for subdoc in subcol.stream():
                        items.append((subdoc.id, f"{path}/{subcol.id}", subdoc.id))
            else:
                # コレクションの場合 → ドキュメント列挙
                for doc in ref.stream():
                    items.append((doc.id, path, doc.id))
            return items

    def load_item_data(self, collection_path: str, document_id: str) -> dict:
        """
        個別アイテムのデータを読み込む

        Returns:
            {
                "doc": { フィールド },
                "subcollections": { ... }
            }
        """
        parts = collection_path.strip("/").split("/")

        # コレクション参照を構築
        ref = self.db
        for i, part in enumerate(parts):
            if i % 2 == 0:
                ref = ref.collection(part)
            else:
                ref = ref.document(part)

        # 最後がコレクションならドキュメントを取得
        if hasattr(ref, 'document'):
            doc_ref = ref.document(document_id)
        else:
            doc_ref = ref

        doc = doc_ref.get()
        if not doc.exists:
            return {"doc": {}, "subcollections": {}}

        doc_data = _serialize(doc.to_dict())

        # サブコレクション
        subcollections = {}
        if hasattr(doc_ref, 'collections'):
            for subcol in doc_ref.collections():
                subcol_data = {}
                for subdoc in subcol.stream():
                    subcol_data[subdoc.id] = _serialize(subdoc.to_dict())
                subcollections[subcol.id] = subcol_data

        return {"doc": doc_data, "subcollections": subcollections}

    def delete_document(self, collection_path: str, document_id: str):
        """ドキュメントを削除 (サブコレクションも再帰削除)"""
        parts = collection_path.strip("/").split("/")

        ref = self.db
        for i, part in enumerate(parts):
            if i % 2 == 0:
                ref = ref.collection(part)
            else:
                ref = ref.document(part)

        if hasattr(ref, 'document'):
            doc_ref = ref.document(document_id)
        else:
            doc_ref = ref

        _delete_document_recursive(doc_ref)
        logger.info(f"Firestoreドキュメント削除: {collection_path}/{document_id}")


def _delete_document_recursive(doc_ref):
    """ドキュメントとサブコレクションを再帰削除"""
    # サブコレクションを先に削除
    for subcol in doc_ref.collections():
        for subdoc in subcol.stream():
            _delete_document_recursive(subdoc.reference)
    # ドキュメント削除
    doc_ref.delete()


def parse_firestore_path(path: str) -> tuple[str, str, bool]:
    """
    Firestoreパスを分解

    Args:
        path: "collection/document" または "collection/document/~"

    Returns:
        (collection, document, is_split_mode)
    """
    path = path.strip("/")
    is_split = path.endswith("/~") or path.endswith("~")
    if is_split:
        path = path.rstrip("~").rstrip("/")

    parts = path.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1], is_split
    elif len(parts) == 1:
        return parts[0], "", is_split
    return "", "", is_split


def get_split_base_path(path: str) -> str:
    """スプリットモードのベースパスを取得 (末尾の/~を除去)"""
    path = path.strip("/")
    if path.endswith("~"):
        path = path[:-1].rstrip("/")
    return path


def convert_to_json_string(data: dict) -> str:
    """データをJSON文字列に変換"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def get_loader_from_credential(encrypted_json: str) -> ExternalDataLoader:
    """暗号化されたJSONからローダーを作成"""
    decrypted = decrypt(encrypted_json)
    return ExternalDataLoader(decrypted)


# --- 後方互換用関数 (既存コードとの互換) ---

def load_external_data(
    data_path: str,
    firebase_key_json_enc: Optional[str] = None,
) -> tuple[str, list]:
    """
    外部データを読み込む (後方互換)

    Returns: (data_str, split_items)
    """
    if not data_path or not firebase_key_json_enc:
        return "", []

    try:
        loader = get_loader_from_credential(firebase_key_json_enc)
        base_path = get_split_base_path(data_path)
        is_split = data_path.strip("/").endswith("~")

        if is_split:
            # スプリットモード
            items = loader.list_subcollection_or_documents(base_path)
            split_items = []
            for item_name, col_path, doc_id in items:
                item_data = loader.load_item_data(col_path, doc_id)
                split_items.append((item_name, convert_to_json_string(item_data)))

            # 全データ (プレビュー用)
            all_data = {name: json.loads(data_str) for name, data_str in split_items}
            return convert_to_json_string(all_data), split_items
        else:
            # シングルモード
            collection, document, _ = parse_firestore_path(data_path)
            if collection and document:
                data = loader.load_data(collection, document)
                return convert_to_json_string(data), []
            elif collection:
                # コレクション全体
                docs = loader.db.collection(collection).stream()
                all_data = {doc.id: _serialize(doc.to_dict()) for doc in docs}
                return convert_to_json_string(all_data), []

        return "", []

    except Exception as e:
        logger.error(f"外部データ読み込みエラー: {data_path} - {e}")
        raise


def _serialize(obj):
    """Firestore の特殊型を JSON シリアライズ可能な形式に変換"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    # Firestore Timestamp / DatetimeWithNanoseconds
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    # GeoPoint
    if hasattr(obj, 'latitude') and hasattr(obj, 'longitude'):
        return {"lat": obj.latitude, "lng": obj.longitude}
    # DocumentReference
    if hasattr(obj, 'path'):
        return obj.path
    # bytes
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    # その他のプリミティブ型
    return obj
