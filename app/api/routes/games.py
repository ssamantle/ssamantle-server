import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import redis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.config import get_settings
from app.db.database import get_db
from app.db.models import Game, Participant
from app.schemas.game import (
    CreateGameRequest,
    CreateGameResponse,
    GamePollingResponse,
    GameResultResponse,
    GameStatusResponse,
    GuessRequest,
    GuessResponse,
    JoinGameRequest,
    JoinGameResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    MessageResponse,
    ParticipantResult,
    UpdateEndtimeRequest,
    UpdateWordRequest,
)
from app.vectors import VectorDB

router = APIRouter(prefix="/api/games", tags=["games"])

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
    """세션이 없으면 401"""
    if not request.session.get("nickname"):
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")
    return request.session


def get_host_session(request: Request, game_id: int) -> dict:
    """호스트 세션 검증"""
    session = get_session(request)
    if not session.get("is_host") or session.get("game_id") != game_id:
        raise HTTPException(status_code=403, detail="호스트만 수행할 수 있습니다.")
    return session


# ─── 게임 상태 자동 전환 ──────────────────────────────────────
def sync_game_status(game: Game, db: Session) -> str:
    """
    started_at / ended_at 기준으로 상태를 자동 전환하고 DB에 반영한다.
    실제 상태 문자열을 반환한다.
    """
    if game.status == "ENDED":
        return "ENDED"

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    new_status = game.status

    if game.ended_at and now >= game.ended_at:
        new_status = "ENDED"
    elif game.started_at and now >= game.started_at:
        new_status = "ACTIVE"

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


def _get_game_or_404(game_id: int, db: Session) -> Game:
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다.")
    return game


# ═══════════════════════════════════════════════════════════════
# 게임 시작하기 (Host)  POST /api/games
# ═══════════════════════════════════════════════════════════════
@router.post("", response_model=CreateGameResponse, status_code=201)
def create_game(
    body: CreateGameRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not body.hostname.strip():
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")
    if not body.targetWord.strip():
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")

    session_id = str(uuid.uuid4())

    # 초기 상태: startTime이 현재보다 이전이면 바로 ACTIVE
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if body.startTime and body.startTime.replace(tzinfo=None) <= now:
        initial_status = "ACTIVE"
    else:
        initial_status = "WAITING"

    game = Game(
        hostname=body.hostname.strip(),
        host_session_id=session_id,
        target_word=body.targetWord.strip(),
        status=initial_status,
        started_at=body.startTime,
        ended_at=body.endTime,
    )
    db.add(game)
    db.commit()
    db.refresh(game)

    # 세션 설정
    request.session["session_id"] = session_id
    request.session["nickname"] = body.hostname.strip()
    request.session["game_id"] = game.id
    request.session["is_host"] = True

    return CreateGameResponse(gameId=game.id)


# ═══════════════════════════════════════════════════════════════
# 게임 참가하기 (User)  POST /api/games/{gameId}/join
# ═══════════════════════════════════════════════════════════════
@router.post("/{game_id}/join", response_model=JoinGameResponse)
def join_game(
    game_id: int,
    body: JoinGameRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    game = _get_game_or_404(game_id, db)
    sync_game_status(game, db)

    if game.status == "ENDED":
        raise HTTPException(status_code=400, detail="이미 종료된 게임입니다.")

    nickname = body.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")

    # 같은 게임 내 닉네임 중복 확인
    dup = (
        db.query(Participant)
        .filter(Participant.game_id == game_id, Participant.nickname == nickname)
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail="이미 사용 중인 닉네임입니다.")

    session_id = str(uuid.uuid4())
    participant = Participant(
        game_id=game_id,
        nickname=nickname,
        session_id=session_id,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)

    # 세션 설정
    request.session["session_id"] = session_id
    request.session["nickname"] = nickname
    request.session["game_id"] = game_id
    request.session["is_host"] = False
    request.session["participant_id"] = participant.id

    return JoinGameResponse(gameId=game_id, nickname=nickname)


# ═══════════════════════════════════════════════════════════════
# 참가 대기 폴링  GET /api/games/{gameId}/status
# ═══════════════════════════════════════════════════════════════
@router.get("/{game_id}/status", response_model=GameStatusResponse)
def game_status(game_id: int, db: Session = Depends(get_db)):
    game = _get_game_or_404(game_id, db)
    status = sync_game_status(game, db)
    count = db.query(Participant).filter(Participant.game_id == game_id).count()
    return GameStatusResponse(
        gameId=game_id,
        gameStatus=status,
        participationCount=count,
    )


# ═══════════════════════════════════════════════════════════════
# 게임 시간 수정 (Host)  PATCH /api/games/{gameId}/endtime
# ═══════════════════════════════════════════════════════════════
@router.patch("/{game_id}/endtime", response_model=MessageResponse)
def update_endtime(
    game_id: int,
    body: UpdateEndtimeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    get_host_session(request, game_id)
    game = _get_game_or_404(game_id, db)

    if body.startedAt is not None:
        game.started_at = body.startedAt
    if body.endedAt is not None:
        game.ended_at = body.endedAt

    db.commit()
    return MessageResponse(message="단어가 수정되었습니다.")


# ═══════════════════════════════════════════════════════════════
# 단어 수정 (Host)  PATCH /api/games/{gameId}/word
# ═══════════════════════════════════════════════════════════════
@router.patch("/{game_id}/word", response_model=MessageResponse)
def update_word(
    game_id: int,
    body: UpdateWordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    get_host_session(request, game_id)
    game = _get_game_or_404(game_id, db)

    if game.status != "WAITING":
        raise HTTPException(status_code=400, detail="게임 시작 전에만 단어를 수정할 수 있습니다.")

    if not body.targetWord.strip():
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")

    game.target_word = body.targetWord.strip()
    db.commit()
    return MessageResponse(message="단어가 수정되었습니다.")


# ═══════════════════════════════════════════════════════════════
# 단어 입력  POST /api/games/{gameId}/guess
# ═══════════════════════════════════════════════════════════════
@router.post("/{game_id}/guess", response_model=GuessResponse)
def guess_word(
    game_id: int,
    body: GuessRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = get_session(request)

    game = _get_game_or_404(game_id, db)
    sync_game_status(game, db)

    if game.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="게임이 진행 중이 아닙니다.")

    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")

    # 참가자 조회
    participant_id = session.get("participant_id")
    participant = (
        db.query(Participant)
        .filter(
            Participant.game_id == game_id,
            Participant.nickname == session["nickname"],
        )
        .first()
    )
    if not participant:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    # 유사도 계산
    vdb = get_vector_db()
    word_data = vdb.get_word_vector(word)
    if word_data is None:
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")

    target_data = vdb.get_word_vector(game.target_word)
    if target_data is None:
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.")

    w_vec, w_norm = word_data
    t_vec, t_norm = target_data
    raw_sim = vdb.cosine_similarity(w_vec, w_norm, t_vec, t_norm)
    similarity = round(max(0.0, raw_sim), 4)

    is_correct = word == game.target_word

    # 참가자 최고 유사도 갱신
    if similarity > participant.best_similarity:
        participant.best_similarity = similarity
        participant.closest_word = word
    if is_correct:
        participant.is_correct = True
    db.commit()

    # TODO: Redis 연동 후 주석 제거
    # Redis 리더보드 갱신
    #r = get_redis()
    #r.zadd(f"game:{game_id}:leaderboard", {participant.nickname: participant.best_similarity})
    #r.set(f"game:{game_id}:closest:{participant.nickname}", participant.closest_word or word)

    # 현재 랭킹 조회 (0-indexed → 1-indexed)
    #rank_idx = r.zrevrank(f"game:{game_id}:leaderboard", participant.nickname)
    #game_rank = (rank_idx or 0) + 1

    return GuessResponse(
        word=word,
        similarity=similarity,
        gameRank=1, #game_rank,
        isCorrect=is_correct,
        bestSimilarity=round(participant.best_similarity, 4),
        closestWord=participant.closest_word or word,
    )


# ═══════════════════════════════════════════════════════════════
# 게임 정보 폴링  GET /api/games/{gameId}/polling
# ═══════════════════════════════════════════════════════════════
@router.get("/{game_id}/polling", response_model=GamePollingResponse)
def game_polling(game_id: int, db: Session = Depends(get_db)):
    game = _get_game_or_404(game_id, db)
    status = sync_game_status(game, db)
    count = db.query(Participant).filter(Participant.game_id == game_id).count()

    r = get_redis()
    leaderboard = get_leaderboard(r, game_id)

    return GamePollingResponse(
        gameStatus=status,
        participationCount=count,
        leaderboard=leaderboard,
    )


# ═══════════════════════════════════════════════════════════════
# 리더보드 조회  GET /api/games/{gameId}/leaderboard
# ═══════════════════════════════════════════════════════════════
@router.get("/{game_id}/leaderboard", response_model=LeaderboardResponse)
def leaderboard(game_id: int, db: Session = Depends(get_db)):
    _get_game_or_404(game_id, db)
    r = get_redis()
    return LeaderboardResponse(leaderboard=get_leaderboard(r, game_id))


# ═══════════════════════════════════════════════════════════════
# 결과 조회  GET /api/games/{gameId}/result
# ═══════════════════════════════════════════════════════════════
@router.get("/{game_id}/result", response_model=GameResultResponse)
def game_result(game_id: int, db: Session = Depends(get_db)):
    game = _get_game_or_404(game_id, db)

    participants = (
        db.query(Participant)
        .filter(Participant.game_id == game_id)
        .order_by(Participant.best_similarity.desc())
        .all()
    )

    result_list = [
        ParticipantResult(
            rank=i + 1,
            nickname=p.nickname,
            bestSimilarity=round(p.best_similarity, 4),
            closestWord=p.closest_word,
            isCorrect=p.is_correct,
        )
        for i, p in enumerate(participants)
    ]

    return GameResultResponse(
        targetWord=game.target_word,
        startedAt=game.started_at,
        endedAt=game.ended_at,
        participants=result_list,
    )


# ═══════════════════════════════════════════════════════════════
# Host 직접 종료  POST /api/games/{gameId}/end
# ═══════════════════════════════════════════════════════════════
@router.post("/{game_id}/end", response_model=MessageResponse)
def end_game(
    game_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    session = get_session(request)
    if not session.get("is_host") or session.get("game_id") != game_id:
        return JSONResponse(
            status_code=403,
            content={"message": "호스트만 종료할 수 있습니다."},
        )

    game = _get_game_or_404(game_id, db)
    game.status = "ENDED"
    if not game.ended_at:
        game.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return MessageResponse(message="게임이 종료되었습니다.")
