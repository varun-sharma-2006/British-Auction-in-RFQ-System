from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/british_auction"
    cors_origins: str = "http://localhost:5173"
    closer_interval_seconds: float = 2.0
    run_closer: bool = True

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
