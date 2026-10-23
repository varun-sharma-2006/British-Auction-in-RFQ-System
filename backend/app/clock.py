"""Single source of "now" for the whole backend.

Every time-sensitive decision (is the auction open? is this bid inside the
trigger window?) is taken against the *server* clock, never the client's.
Keeping it behind one function also lets tests freeze time.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
