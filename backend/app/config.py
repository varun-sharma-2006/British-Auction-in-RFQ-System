from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/british_auction"
    cors_origins: str = "http://localhost:5173"
    closer_interval_seconds: float = 2.0
    # In-process closer. Turn off when Celery beat + worker run it instead (docker-compose does this).
    run_closer: bool = True
    # Set to enable Redis pub/sub fan-out (multiple API replicas) and the Celery broker.
    redis_url: str | None = None
    # Name this API instance reports in the X-Served-By header (defaults to hostname:pid). Behind the load
    # balancer it shows which replica answered a request.
    instance_name: str | None = None
    # How often the availability Bloom filters are rebuilt from the database (seconds).
    bloom_rebuild_seconds: float = 300

    # Serverless hosts (Vercel) freeze instances between requests, so background loops can't be relied on:
    # close due auctions opportunistically on incoming API requests (throttled) ...
    close_on_request: bool = False
    close_on_request_every_seconds: float = 5
    # ... and treat an in-memory Bloom filter older than this as stale (rebuilt on the next check).
    bloom_max_age_seconds: float | None = None

    # Demo deployments: keep live auctions available by starting a fresh set when fewer than two are open.
    seed_demo: bool = False
    demo_refresh_every_seconds: float = 60

    # Directory of the built frontend (frontend/dist). When set, the API also serves the SPA: one URL, one container.
    frontend_dist: str | None = None

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres (Render, Neon, Heroku) hands out postgres:// URLs; SQLAlchemy needs the driver named.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("redis_url", "frontend_dist")
    @classmethod
    def empty_is_none(cls, v: str | None) -> str | None:
        return v or None

    # Auth. Override JWT_SECRET in every real deployment.
    jwt_secret: str = "dev-only-change-me-please-32-bytes!!"
    access_token_minutes: int = 12 * 60
    session_cookie: str = "rfq_session"   # HttpOnly cookie the web UI authenticates with

    # Abuse protection for public deployments (tests switch it off).
    rate_limit_enabled: bool = True
    # Vercel Cron sends "Authorization: Bearer $CRON_SECRET"; the nightly demo reset requires it.
    cron_secret: str | None = None
    password_hash_iterations: int = 390_000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
