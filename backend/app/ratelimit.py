"""Small rate limiter for the public demo: sign-up, login, RFQ creation, bids and availability checks.

* With REDIS_URL: a fixed-window counter in Redis (INCR + EXPIRE), shared by every replica.
* Without: an in-process sliding window. On serverless hosts that is per instance, which still blunts
  scripted abuse, and the nightly demo reset cleans up whatever gets through.
Clients are keyed by their session (token) when signed in, otherwise by IP. X-Real-IP is set by our nginx and by Vercel,
so a client can't spoof it there.
"""
import hashlib
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings
from app.errors import DomainError

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _allow_memory(key: str, limit: int, window: float) -> tuple[bool, int]:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False, max(1, int(q[0] + window - now))
        q.append(now)
        return True, 0


def _allow_redis(key: str, limit: int, window: float) -> tuple[bool, int]:
    import redis

    r = redis.from_url(get_settings().redis_url)
    try:
        bucket = int(time.time() // window)
        k = f"rl:{key}:{bucket}"
        n = r.incr(k)
        if n == 1:
            r.expire(k, int(window) + 1)
        return n <= limit, int(window - time.time() % window) + 1
    finally:
        r.close()


def reset() -> None:
    with _lock:
        _hits.clear()


def rate_limit(name: str, limit: int, window_seconds: float, per_user: bool = False):
    """FastAPI dependency: at most `limit` calls per `window_seconds` per client (or per signed-in user)."""

    def dependency(request: Request) -> None:
        s = get_settings()
        if not s.rate_limit_enabled:
            return
        who = client_ip(request)
        if per_user:
            token = request.headers.get("authorization", "") or request.cookies.get(s.session_cookie, "")
            # Stable across processes (unlike hash()), so replicas sharing Redis agree on the key.
            who = f"tok:{hashlib.sha256(token.encode()).hexdigest()[:16]}" if token else who
        key = f"{name}:{who}"
        try:
            ok, retry = (_allow_redis if s.redis_url else _allow_memory)(key, limit, window_seconds)
        except Exception:
            ok, retry = _allow_memory(key, limit, window_seconds)   # Redis down: still limit, per instance
        if not ok:
            raise DomainError(429, f"Too many requests. Please try again in {retry} s.")

    return dependency
