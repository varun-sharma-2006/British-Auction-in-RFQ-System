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
    password_hash_iterations: int = 390_000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
