from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 기본 설정
    app_name: str = "Semantle Server"
    app_version: str = "0.0.1"
    
    # 서버 설정
    host: str = "0.0.0.0"
    port: int = 8000
    
    # 환경
    environment: str = "development"
    debug: bool = True
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # 추가 필드 무시


@lru_cache()
def get_settings() -> Settings:
    """설정 객체 싱글톤"""
    return Settings()
