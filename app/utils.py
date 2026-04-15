import redis
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.config import get_settings
from app.db.enums import GameStatus
from app.db.models import Game
from app.schemas.game import LeaderboardEntry
from app.vectors import VectorDB

settings = get_settings()

# ─── VectorDB 지연 초기화 ─────────────────────────────────────
_vector_db: Optional[VectorDB] = None


def get_vector_db() -> VectorDB:
    global _vector_db
    if _vector_db is None:
        try:
            _vector_db = VectorDB(Path(settings.vector_db_path))
        except FileNotFoundError:
            raise HTTPException(
                status_code=503,
                detail="벡터 데이터베이스를 찾을 수 없습니다.",
            )
    return _vector_db


# ─── Redis 클라이언트 ─────────────────────────────────────────
def get_redis() -> redis.Redis:
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except redis.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Redis에 연결할 수 없습니다.",
        )


# ─── 세션 헬퍼 ───────────────────────────────────────────────
def get_session(request: Request) -> dict:
    if not request.session.get("nickname"):
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")
    return request.session


def get_host_session(request: Request, game_id: int) -> dict:
    session = get_session(request)
    if not session.get("is_host") or session.get("game_id") != game_id:
        raise HTTPException(status_code=403, detail="호스트만 수행할 수 있습니다.")
    return session


# ─── 게임 상태 자동 전환 ──────────────────────────────────────
def sync_game_status(game: Game, db: Session) -> str:
    if game.status == GameStatus.POSTGAME:
        return GameStatus.POSTGAME

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    new_status = game.status

    if game.ended_at and now >= game.ended_at:
        new_status = GameStatus.POSTGAME
    elif game.started_at and now >= game.started_at:
        new_status = GameStatus.INGAME

    if new_status != game.status:
        game.status = new_status
        db.commit()

    return new_status


# ─── Redis 리더보드 헬퍼 ──────────────────────────────────────
def get_leaderboard(r: redis.Redis, game_id: int) -> list[LeaderboardEntry]:
    members = r.zrevrangebyscore(
        f"game:{game_id}:leaderboard", "+inf", "-inf", withscores=True
    )
    result = []
    for i, (nickname, score) in enumerate(members):
        closest = r.get(f"game:{game_id}:closest:{nickname}")
        result.append(
            LeaderboardEntry(
                rank=i + 1,
                nickname=nickname,
                bestSimilarity=round(score, 4),
                closestWord=closest,
            )
        )
    return result


# ─── 게임 조회 ───────────────────────────────────────────────
def get_game_or_404(game_id: int, db: Session) -> Game:
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다.")
    return game
