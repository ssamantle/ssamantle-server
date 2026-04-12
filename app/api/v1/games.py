import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db.database import get_db
from app.db.enums import GameStatus
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
    LeaderboardResponse,
    MessageResponse,
    ParticipantResult,
    UpdateEndtimeRequest,
    UpdateWordRequest,
)
from app.api.routes.games import (
    get_vector_db,
    get_redis,
    get_session,
    sync_game_status,
    get_leaderboard,
    _get_game_or_404,
)

router = APIRouter(prefix="/api/v1/games", tags=["games-v1"])

V1_GAME_ID = 1


def get_host_session_v1(request: Request) -> dict:
    session = get_session(request)
    if not session.get("is_host") or session.get("game_id") != V1_GAME_ID:
        raise HTTPException(status_code=403, detail="호스트만 수행할 수 있습니다.")
    return session


# ═══════════════════════════════════════════════════════════════
# 게임 생성 (Host)  POST /api/v1/games
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

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if body.startTime and body.startTime.replace(tzinfo=None) <= now:
        initial_status = GameStatus.INGAME
    else:
        initial_status = GameStatus.PREGAME

    # 기존 게임이 있으면 덮어쓰기, 없으면 생성
    game = db.query(Game).filter(Game.id == V1_GAME_ID).first()
    if game:
        game.hostname = body.hostname.strip()
        game.host_session_id = session_id
        game.target_word = body.targetWord.strip()
        game.status = initial_status
        game.started_at = body.startTime
        game.ended_at = body.endTime
        game.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.query(Participant).filter(Participant.game_id == V1_GAME_ID).delete()
    else:
        game = Game(
            id=V1_GAME_ID,
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

    request.session["session_id"] = session_id
    request.session["nickname"] = body.hostname.strip()
    request.session["game_id"] = V1_GAME_ID
    request.session["is_host"] = True

    return CreateGameResponse(gameId=V1_GAME_ID)


# ═══════════════════════════════════════════════════════════════
# 게임 참가  POST /api/v1/games/join
# ═══════════════════════════════════════════════════════════════
@router.post("/join", response_model=JoinGameResponse)
def join_game(
    body: JoinGameRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    game = _get_game_or_404(V1_GAME_ID, db)
    sync_game_status(game, db)

    if game.status == GameStatus.POSTGAME:
        raise HTTPException(status_code=400, detail="이미 종료된 게임입니다.")

    nickname = body.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")

    dup = (
        db.query(Participant)
        .filter(Participant.game_id == V1_GAME_ID, Participant.nickname == nickname)
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail="이미 사용 중인 닉네임입니다.")

    session_id = str(uuid.uuid4())
    participant = Participant(game_id=V1_GAME_ID, nickname=nickname, session_id=session_id)
    db.add(participant)
    db.commit()
    db.refresh(participant)

    request.session["session_id"] = session_id
    request.session["nickname"] = nickname
    request.session["game_id"] = V1_GAME_ID
    request.session["is_host"] = False
    request.session["participant_id"] = participant.id

    return JoinGameResponse(gameId=V1_GAME_ID, nickname=nickname)


# ═══════════════════════════════════════════════════════════════
# 게임 상태 폴링  GET /api/v1/games/status
# ═══════════════════════════════════════════════════════════════
@router.get("/status", response_model=GameStatusResponse)
def game_status(db: Session = Depends(get_db)):
    game = _get_game_or_404(V1_GAME_ID, db)
    status = sync_game_status(game, db)
    count = db.query(Participant).filter(Participant.game_id == V1_GAME_ID).count()
    return GameStatusResponse(gameId=V1_GAME_ID, gameStatus=status, participationCount=count)


# ═══════════════════════════════════════════════════════════════
# 시간 수정 (Host)  PATCH /api/v1/games/time
# ═══════════════════════════════════════════════════════════════
@router.patch("/time", response_model=MessageResponse)
def update_endtime(
    body: UpdateEndtimeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    get_host_session_v1(request)
    game = _get_game_or_404(V1_GAME_ID, db)

    if body.startedAt is not None:
        game.started_at = body.startedAt
    if body.endedAt is not None:
        game.ended_at = body.endedAt

    db.commit()
    return MessageResponse(message="시간이 수정되었습니다.")


# ═══════════════════════════════════════════════════════════════
# 단어 수정 (Host)  PATCH /api/v1/games/word
# ═══════════════════════════════════════════════════════════════
@router.patch("/word", response_model=MessageResponse)
def update_word(
    body: UpdateWordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    get_host_session_v1(request)
    game = _get_game_or_404(V1_GAME_ID, db)

    if game.status != GameStatus.PREGAME:
        raise HTTPException(status_code=400, detail="게임 시작 전에만 단어를 수정할 수 있습니다.")

    if not body.targetWord.strip():
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")

    game.target_word = body.targetWord.strip()
    db.commit()
    return MessageResponse(message="단어가 수정되었습니다.")


# ═══════════════════════════════════════════════════════════════
# 단어 추측  POST /api/v1/games/guess
# ═══════════════════════════════════════════════════════════════
@router.post("/guess", response_model=GuessResponse)
def guess_word(
    body: GuessRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = get_session(request)

    game = _get_game_or_404(V1_GAME_ID, db)
    sync_game_status(game, db)

    if game.status != GameStatus.INGAME:
        raise HTTPException(status_code=400, detail="게임이 진행 중이 아닙니다.")

    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="잘못된 요청입니다.")

    participant = (
        db.query(Participant)
        .filter(Participant.game_id == V1_GAME_ID, Participant.nickname == session["nickname"])
        .first()
    )
    if not participant:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

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

    if similarity > participant.best_similarity:
        participant.best_similarity = similarity
        participant.closest_word = word
    if is_correct:
        participant.is_correct = True
    db.commit()

    r = get_redis()
    r.zadd(f"game:{V1_GAME_ID}:leaderboard", {participant.nickname: participant.best_similarity})
    r.set(f"game:{V1_GAME_ID}:closest:{participant.nickname}", participant.closest_word or word)

    rank_idx = r.zrevrank(f"game:{V1_GAME_ID}:leaderboard", participant.nickname)
    game_rank = (rank_idx or 0) + 1

    return GuessResponse(
        word=word,
        similarity=similarity,
        gameRank=game_rank,
        isCorrect=is_correct,
        bestSimilarity=round(participant.best_similarity, 4),
        closestWord=participant.closest_word or word,
    )


# ═══════════════════════════════════════════════════════════════
# 게임 정보 폴링  GET /api/v1/games/polling
# ═══════════════════════════════════════════════════════════════
@router.get("/polling", response_model=GamePollingResponse)
def game_polling(db: Session = Depends(get_db)):
    game = _get_game_or_404(V1_GAME_ID, db)
    status = sync_game_status(game, db)
    count = db.query(Participant).filter(Participant.game_id == V1_GAME_ID).count()

    r = get_redis()
    leaderboard = get_leaderboard(r, V1_GAME_ID)

    return GamePollingResponse(gameStatus=status, participationCount=count, leaderboard=leaderboard)


# ═══════════════════════════════════════════════════════════════
# 리더보드  GET /api/v1/games/leaderboard
# ═══════════════════════════════════════════════════════════════
@router.get("/leaderboard", response_model=LeaderboardResponse)
def leaderboard(db: Session = Depends(get_db)):
    _get_game_or_404(V1_GAME_ID, db)
    r = get_redis()
    return LeaderboardResponse(leaderboard=get_leaderboard(r, V1_GAME_ID))


# ═══════════════════════════════════════════════════════════════
# 결과 조회  GET /api/v1/games/result
# ═══════════════════════════════════════════════════════════════
@router.get("/result", response_model=GameResultResponse)
def game_result(db: Session = Depends(get_db)):
    game = _get_game_or_404(V1_GAME_ID, db)

    participants = (
        db.query(Participant)
        .filter(Participant.game_id == V1_GAME_ID)
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
# Host 직접 종료  POST /api/v1/games/end
# ═══════════════════════════════════════════════════════════════
@router.post("/end", response_model=MessageResponse)
def end_game(
    request: Request,
    db: Session = Depends(get_db),
):
    session = get_session(request)
    if not session.get("is_host") or session.get("game_id") != V1_GAME_ID:
        return JSONResponse(status_code=403, content={"message": "호스트만 종료할 수 있습니다."})

    game = _get_game_or_404(V1_GAME_ID, db)
    game.status = GameStatus.POSTGAME
    if not game.ended_at:
        game.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return MessageResponse(message="게임이 종료되었습니다.")
