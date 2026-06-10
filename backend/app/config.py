from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ENV: Literal["development", "staging", "production"] = "development"

    DATABASE_URL: str = "postgresql+asyncpg://pm_user:pm_secret@localhost:5432/pm_ontology"
    REDIS_URL: str = "redis://localhost:6379/0"
    FUSEKI_URL: str = "http://localhost:3030/pm-ontology"
    FUSEKI_ADMIN_USER: str = "admin"
    FUSEKI_ADMIN_PASSWORD: str = "fuseki_secret"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-nano"

    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""

    GITHUB_WEBHOOK_SECRET: str = ""

    # Google Slides / Drive (OAuth2)
    GOOGLE_CLIENT_SECRET_FILE: str = ""   # GCP Console에서 다운로드한 OAuth2 클라이언트 JSON
    GOOGLE_TOKEN_FILE: str = "secrets/google-token.json"  # 최초 인증 후 자동 저장되는 토큰 파일
    GOOGLE_SLIDES_FOLDER_ID: str = ""     # Drive 폴더 ID (선택, 비어있으면 루트)

    # GitLab
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: str = ""
    GITLAB_NAMESPACE: str = ""  # 그룹 path 또는 유저명

    # 알림 API
    ALERT_API_URL: str = "http://dweax.iptime.org:50009"
    ALERT_API_INTERNAL_TOKEN: str = ""

    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8시간

    CORS_ORIGINS: list[str] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://dweax.iptime.org:50010",
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
