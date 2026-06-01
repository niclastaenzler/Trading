"""Symmetric encryption for broker credentials at rest.

Broker API keys/passwords are NEVER stored in plaintext. We use Fernet
(AES-128-CBC + HMAC). The key comes from `ENCRYPTION_KEY`; in development a
deterministic key is derived so the app still boots, but production refuses to
start without an explicit key (enforced in `main.py`).
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        # Dev fallback: derive a stable key. Logged loudly elsewhere.
        digest = hashlib.sha256(b"dev-only-insecure-key").digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Could not decrypt credential — wrong ENCRYPTION_KEY?")
