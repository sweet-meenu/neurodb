from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

import jwt

SECRET_KEY = os.environ.get("NEURODB_SECRET_KEY", "dev-insecure-secret-change-me-in-production-0123456789")
JWT_ALGORITHM = "HS256"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected, actual)


def issue_session_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + SESSION_TTL_SECONDS}
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_session_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def generate_api_key() -> str:
    return f"ndb_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
