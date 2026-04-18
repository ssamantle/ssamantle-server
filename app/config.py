from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 기본 설정
    app_name: str = "Semantle Server"
    app_version: str = "0.0.2"

    # 서버 설정
    host: str = "0.0.0.0"
    port: int = 8000

    # 환경
    environment: str = "development"
    debug: bool = True

    # FastText 벡터 설정 (절대 경로)
    vector_db_path: str = str(Path(__file__).parent.parent / "data" / "vectors.db")
    words_list_path: str = str(Path(__file__).parent.parent / "data" / "filtered_words.txt")
    secrets_path: str = str(Path(__file__).parent.parent / "data" / "daily_secrets_2026.json")

    # 데이터베이스
    database_url: str = "sqlite:///./semantle.db"

    # Redis
    redis_url: str = "redis://localhost:6380/0"

    # 세션
    secret_key: str = "dev-secret-key-change-in-production"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """설정 객체 싱글톤"""
    return Settings()
