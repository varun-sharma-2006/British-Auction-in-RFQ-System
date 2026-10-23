import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DomainError
from app.models import User, UserRole
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise DomainError(401, "Not signed in")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise DomainError(401, "Session expired, please sign in again") from None
    except jwt.PyJWTError:
        raise DomainError(401, "Invalid access token") from None
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise DomainError(401, "Account no longer exists")
    return user


def require_buyer(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.BUYER:
        raise DomainError(403, "Only buyers can do this")
    return user


def require_supplier(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.SUPPLIER:
        raise DomainError(403, "Only suppliers can submit quotes")
    return user
