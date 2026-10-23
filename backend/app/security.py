"""Password hashing (PBKDF2-SHA256, stdlib) and JWT access tokens (PyJWT, HS256)."""
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt

from app import clock
from app.config import get_settings

_ALGO = "pbkdf2_sha256"


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or get_settings().password_hash_iterations
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_ALGO}${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def create_access_token(user_id: int, role: str) -> str:
    s = get_settings()
    now = clock.utcnow()
    payload = {"sub": str(user_id), "role": role, "iat": now,
               "exp": now + timedelta(minutes=s.access_token_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on a bad signature, a malformed token or an expired one."""
    # Expiry is checked against our own clock so tests (and the server) share one notion of "now".
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"], options={"verify_exp": False, "verify_iat": False})
    if payload["exp"] <= clock.utcnow().timestamp():
        raise jwt.ExpiredSignatureError("Token expired")
    return payload
