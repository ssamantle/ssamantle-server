from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path
import os


BASE_DIR = Path(__file__).parent.parent.resolve()


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 기본 설정
    app_name: str = "Semantle Server"
    app_version: str = "1.0.0"
    app_description: str = "FastAPI 기반 백엔드 서비스"

    # 서버 설정
    host: str = "0.0.0.0"
    port: int = 8000

    # 환경
    debug: bool = os.environ['DEBUG'].lower() in ['true', '1']

    # FastText 벡터 설정 (절대 경로)
    vector_db_path: str = str(BASE_DIR / "data" / "vectors.db")
    words_list_path: str = str(BASE_DIR / "data" / "filtered_words.txt")
    secrets_path: str = str(BASE_DIR / "data" / "daily_secrets_2026.json")

    # 데이터베이스
    database_url: str = os.environ['DATABASE_URL']
    redis_url: str = os.environ['REDIS_URL']

    # 세션
    secret_key: str = os.environ['SECRET']

    # 로깅
    log_dir: str = str(BASE_DIR / "data" / "logs")
    log_file_name: str = "app.log"
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 100

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """설정 객체 싱글톤"""
    return Settings()
