from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://redis:6379/0"

    storage_backend: Literal["s3", "memory"] = "s3"
    s3_endpoint_url: str | None = None
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "acadledger-uploads"
    s3_region: str = "us-east-1"

    jwt_secret: str
    jwt_expire_minutes: int = 480
    cookie_secure: bool = False

    apaar_client: Literal["mock"] = "mock"

    max_upload_bytes: int = 25 * 1024 * 1024
    max_upload_rows: int = 200_000

    @field_validator("jwt_secret")
    @classmethod
    def _secret_is_not_guessable(cls, value: str) -> str:
        # Anyone who knows this value can sign themselves in as anyone, so refuse to start
        # with the placeholder from .env.example or anything short.
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters (openssl rand -hex 32)")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
