import hashlib
import os
from base64 import b64decode, b64encode

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings


def _derive_key() -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"mxvault-salt", iterations=100000)
    return b64encode(kdf.derive(settings.encryption_key.encode()))


_fernet = Fernet(_derive_key())


def encrypt_password(password: str) -> str:
    return _fernet.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return b64encode(salt + key).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        decoded = b64decode(stored_hash.encode())
        salt = decoded[:32]
        key = decoded[32:]
        new_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return key == new_key
    except Exception:
        return False
