from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db.database import create_tables
from app.api.routes import health, similarity
from app.api.routes import users  # , games
from app.api.v1 import games as games_v1
from app.api.v1 import auth as auth_v1
from app.utils.logging import (
    reset_request_session_id,
    resolve_session_id_from_request,
    set_request_session_id,
    setup_logging,
)

settings = get_settings()
setup_logging(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title=settings.app_name,
    description="FastAPI 기반 백엔드 서비스",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)


@app.middleware("http")
async def bind_request_logging_context(request: Request, call_next):
    session_id = resolve_session_id_from_request(request)
    token = set_request_session_id(session_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_session_id(token)
    return response

# 세션 미들웨어 (쿠키 이름: SESSION)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="SESSION",
    https_only=False,  # 개발 환경 — 운영에서는 True로 변경
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(health.router)

app.include_router(similarity.router)
app.include_router(users.router)
# app.include_router(games.router)
app.include_router(games_v1.router)
app.include_router(auth_v1.router)


@app.on_event("startup")
def startup():
    create_tables()


@app.get("/")
async def root():
    return {
        "message": f"{settings.app_name}에 오신 것을 환영합니다!",
        "version": settings.app_version,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
