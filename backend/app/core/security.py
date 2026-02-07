import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings


def _get_key() -> bytes:
    """AESキーをバイト列で取得"""
    key_hex = settings.AES_KEY
    if not key_hex:
        raise ValueError("AES_KEY が設定されていません")
    return bytes.fromhex(key_hex)


def encrypt(plaintext: str) -> str:
    """AES-256-GCM暗号化 → base64エンコード文字列"""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # nonce + ciphertext を結合してbase64
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt(encrypted: str) -> str:
    """base64文字列 → AES-256-GCM復号"""
    key = _get_key()
    aesgcm = AESGCM(key)
    data = base64.b64decode(encrypted)
    nonce = data[:12]
    ciphertext = data[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
