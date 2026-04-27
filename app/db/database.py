from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

settings = get_settings()

# SQLite는 check_same_thread=False 필요
engine = create_engine(
    settings.database_url,
    pool_size=50,
    max_overflow=50,
    pool_timeout=60,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """앱 시작 시 테이블 생성"""
    from app.db import models  # noqa: F401 - 모델 import로 Base에 등록
    Base.metadata.create_all(bind=engine)
