"""Live "is this taken?" checks for sign-up email, supplier company name and RFQ reference ID.

Flow for each check:
  1. Bloom filter says *definitely not seen*  -> available, answered without a database query.
  2. Bloom filter says *maybe*                -> confirm with an indexed database lookup
                                                 (filters have false positives, never false negatives).
The database UNIQUE constraints remain the final authority on insert; this is a fast, advisory check
for the forms.

Keeping the filter complete:
  * every insert made through the API adds its value immediately (`note_added`);
  * the filter is rebuilt from the database at startup and every few minutes, which also picks up
    rows written outside the API (seed script, another process) and drops deleted values;
  * with REDIS_URL set, the bits live in Redis, so all API replicas share one filter.
"""
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Rfq, Supplier, User
from app.services.bloom import BloomFilter, MemoryBits, RedisBits

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Kind:
    name: str
    normalize: Callable[[str], str]
    column: object                     # the DB column the value lives in
    case_insensitive: bool


KINDS = {
    "email": Kind("email", lambda v: v.strip().lower(), User.email, True),
    "company": Kind("company", lambda v: v.strip().lower(), Supplier.name, True),   # same rule as sign-up
    "reference_id": Kind("reference_id", lambda v: v.strip(), Rfq.reference_id, False),
}

_filters: dict[str, BloomFilter] = {}
stats: Counter = Counter()   # answered_by_bloom, confirmed_taken, false_positive, fallback


def _redis_client():
    import redis  # local import: only needed when REDIS_URL is set

    return redis.from_url(get_settings().redis_url)


def get_filter(kind: str) -> BloomFilter:
    if kind not in _filters:
        if get_settings().redis_url:
            def store(bits, kind=kind):
                return RedisBits(_redis_client, f"bloom:{kind}")
        else:
            store = MemoryBits
        _filters[kind] = BloomFilter(store, capacity=100_000, error_rate=0.01)
    return _filters[kind]


def reset_filters() -> None:
    """Forget filter objects (tests switch storage backends)."""
    _filters.clear()
    stats.clear()


def _db_taken(db: Session, kind: Kind, value: str) -> bool:
    col = kind.column
    expr = func.lower(col) == value if kind.case_insensitive else col == value
    return db.execute(select(col).where(expr).limit(1)).first() is not None


def check(db: Session, kind_name: str, raw: str) -> tuple[bool, str]:
    """Returns (available, how it was decided: 'bloom' | 'database')."""
    kind = KINDS[kind_name]
    value = kind.normalize(raw)
    try:
        maybe = get_filter(kind_name).might_contain(value)
    except Exception:
        log.exception("Bloom filter unavailable; falling back to the database")
        stats["fallback"] += 1
        return not _db_taken(db, kind, value), "database"
    if not maybe:
        stats["answered_by_bloom"] += 1
        return True, "bloom"
    taken = _db_taken(db, kind, value)
    stats["confirmed_taken" if taken else "false_positive"] += 1
    return not taken, "database"


def note_added(kind_name: str, raw: str) -> None:
    try:
        get_filter(kind_name).add(KINDS[kind_name].normalize(raw))
    except Exception:  # never fail a write because the advisory filter is unreachable
        log.exception("Could not add %s to the Bloom filter", kind_name)


def rebuild_all(db: Session) -> dict[str, int]:
    counts = {}
    for name, kind in KINDS.items():
        values = (kind.normalize(v) for (v,) in db.execute(select(kind.column)))
        counts[name] = get_filter(name).rebuild(values)
    return counts
