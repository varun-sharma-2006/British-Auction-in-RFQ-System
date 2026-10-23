from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.errors import DomainError
from app.models import Supplier, User, UserRole
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password
from app.services import availability

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role,
                   supplier_id=user.supplier_id, supplier_name=user.supplier.name if user.supplier else None)


def _token(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id, user.role.value), user=user_out(user))


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none():
        raise DomainError(409, "An account with this email already exists")

    supplier = None
    if body.role == UserRole.SUPPLIER:
        name = body.company_name.strip()
        # Colleagues from the same carrier share one supplier company (and one place in the ranking).
        supplier = db.execute(select(Supplier).where(func.lower(Supplier.name) == name.lower())).scalar_one_or_none()
        if supplier is None:
            supplier = Supplier(name=name, contact_email=email)
            db.add(supplier)
            db.flush()

    user = User(email=email, full_name=body.full_name.strip(), password_hash=hash_password(body.password),
                role=body.role, supplier_id=supplier.id if supplier else None)
    db.add(user)
    db.commit()
    availability.note_added("email", email)
    if supplier is not None:
        availability.note_added("company", supplier.name)
    return _token(user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(func.lower(User.email) == body.email.lower())).scalar_one_or_none()
    # Same message for unknown email and wrong password: login doesn't tell an attacker which part was wrong.
    # (Sign-up and its availability check necessarily reveal whether an email is registered; a real
    # deployment would rate-limit those endpoints.)
    if user is None or not verify_password(body.password, user.password_hash):
        raise DomainError(401, "Incorrect email or password")
    return _token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)
