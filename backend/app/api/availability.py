from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_buyer
from app.db import get_db
from app.models import User
from app.ratelimit import rate_limit
from app.services import availability

router = APIRouter(prefix="/api/availability", tags=["availability"],
                   dependencies=[Depends(rate_limit("availability", 60, 60))])


class Availability(BaseModel):
    value: str
    available: bool
    checked_by: str   # "bloom": answered from the Bloom filter alone; "database": confirmed with a query


def _check(db: Session, kind: str, value: str) -> Availability:
    ok, how = availability.check(db, kind, value)
    return Availability(value=value, available=ok, checked_by=how)


# Public: used by the sign-up form before the person has an account.
@router.get("/email", response_model=Availability)
def email(value: str = Query(min_length=3, max_length=254), db: Session = Depends(get_db)):
    return _check(db, "email", value)


@router.get("/company", response_model=Availability)
def company(value: str = Query(min_length=2, max_length=120), db: Session = Depends(get_db)):
    """available=false means the company exists: a new supplier user will join it."""
    return _check(db, "company", value)


@router.get("/reference-id", response_model=Availability)
def reference_id(value: str = Query(min_length=1, max_length=40), db: Session = Depends(get_db),
                 _: User = Depends(require_buyer)):
    return _check(db, "reference_id", value)


@router.get("/stats")
def stats(_: User = Depends(require_buyer)):
    """How many checks the filter answered on its own vs. needed the database."""
    return dict(availability.stats)
