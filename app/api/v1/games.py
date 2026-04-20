import logging
import uuid, json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, selectinload
from starlette.requests import Request

from app.db.database import get_db
from app.db.enums import GameStatus
from app.db.models import Game, GuessHistory, Participant
from app.schemas.game import (
    CreateGameRequest,
    CreateGameResponse,
    GameInfoResponse,
    GameResultResponse,
    GameStatusResponse,
    GuessHistoryItem,
    GuessRequest,
    GuessResponse,
    JoinGameRequest,
    JoinGameResponse,
    LeaderboardResponse,
    MessageResponse,
    ParticipantResult,
    UpdateEndtimeRequest,
    UpdateWordRequest,
    UserInfo,
)
from app.utils import (
    build_submission_detail,
    get_best_guess,
    get_latest_guess,
    get_vector_db,
    get_redis,
    get_session,
    sync_game_status,
    get_game_or_404,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/games", tags=["games-v1"])

V1_GAME_ID = 1


def get_host_session_v1(request: Request) -> dict:
    session = get_session(request)
    if not session.get("is_host") or session.get("game_id") != V1_GAME_ID:
        raise HTTPException(status_code=403, detail="호스트만 수행할 수 있습니다.")
    return session


def refresh_vector_similarities(target_word: str) -> int:
    try:
        vdb = get_vector_db()
        return vdb.update_similarities(target_word)
    except ValueError:
        raise HTTPException(status_code=400, detail="정답 단어가 벡터 DB에 없습니다.")


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
        raise HTTPException(status_code=400, detail="요청 본문에 hostname 필드는 필수입니다.")
    if not body.targetWord.strip():
        raise HTTPException(status_code=400, detail="요청 본문에 targetWord 필드는 필수입니다.")

    vdb = get_vector_db()
    if not vdb.word_exists(body.targetWord.strip()):
        logger.warning("게임 생성 실패 - 사전에 없는 단어: '%s' (host=%s)", body.targetWord.strip(), body.hostname.strip())
        raise HTTPException(status_code=404, detail=f"'{body.targetWord.strip()}'은(는) 사전에 없는 단어입니다.")

    session_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if body.startTime and body.startTime.replace(tzinfo=None) <= now:
        initial_status = GameStatus.INGAME
    else:
        initial_status = GameStatus.PREGAME

    # 기존 게임이 있으면 덮어쓰기, 없으면 생성
    game = db.query(Game).filter(Game.id == V1_GAME_ID).first()
    if game:
        logger.info("게임 재생성 (덮어쓰기) - host=%s, targetWord=%s, status=%s", body.hostname.strip(), body.targetWord.strip(), initial_status)
        game.hostname = body.hostname.strip()
        game.host_session_id = session_id
        game.target_word = body.targetWord.strip()
        game.status = initial_status
        game.started_at = body.startTime
        game.ended_at = body.endTime
        game.created_at = datetime.now(timezone.utc).replace(tzinfo=None) # TODO: TIMEZONE을 한국시간으로 변경
        for participant in db.query(Participant).filter(Participant.game_id == V1_GAME_ID).all():
            db.delete(participant)
        r = get_redis()
        r.delete(f"game:{V1_GAME_ID}:leaderboard")
        r.delete(f"game:{V1_GAME_ID}:participants")
    else:
        logger.info("게임 생성 - host=%s, targetWord=%s, status=%s", body.hostname.strip(), body.targetWord.strip(), initial_status)
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

    refresh_vector_similarities(game.target_word)

    request.session["session_id"] = session_id # TODO: sessionId는 쿠키로 전송하자.
    request.session["nickname"] = body.hostname.strip()
    request.session["game_id"] = V1_GAME_ID
    request.session["is_host"] = True

    return CreateGameResponse(gameId=V1_GAME_ID, sessionId=session_id)


# ═══════════════════════════════════════════════════════════════
# 게임 참가  POST /api/v1/games/join
# ═══════════════════════════════════════════════════════════════
@router.post("/join", response_model=JoinGameResponse)
def join_game(
    body: JoinGameRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    game = get_game_or_404(V1_GAME_ID, db)
    sync_game_status(game, db)

    if game.status == GameStatus.POSTGAME:
        logger.warning("게임 참가 실패 - 이미 종료된 게임 (nickname=%s)", body.nickname.strip())
        raise HTTPException(status_code=409, detail="이미 종료된 게임입니다.")

    nickname = body.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="요청 본문에 nickname 필드는 필수입니다.")

    dup = (
        db.query(Participant)
        .filter(Participant.game_id == V1_GAME_ID, Participant.nickname == nickname)
        .first()
    )
    if dup:
        logger.warning("게임 참가 실패 - 닉네임 중복: '%s'", nickname)
        raise HTTPException(status_code=409, detail="이미 사용 중인 닉네임입니다.")

    session_id = str(uuid.uuid4())
    participant = Participant(game_id=V1_GAME_ID, nickname=nickname, session_id=session_id)
    db.add(participant)
    db.commit()
    db.refresh(participant)

    r = get_redis()

    # Redis 리더보드에 초기값 등록
    r.zadd(f"game:{V1_GAME_ID}:leaderboard", {participant.id: 0.0}, nx=True) # nx=True로 기존 참가자 점수 덮어쓰기 방지

    # Hash: 참가자 정보 저장
    r.hset(f"game:{V1_GAME_ID}:participants", participant.id, json.dumps({
        "nickname": nickname,
        "sessionId": session_id,
    }))

    request.session["session_id"] = session_id
    request.session["nickname"] = nickname
    request.session["game_id"] = V1_GAME_ID
    request.session["is_host"] = False
    request.session["participant_id"] = participant.id

    logger.info("게임 참가 - nickname=%s, participantId=%s", nickname, participant.id)
    return JoinGameResponse(gameId=V1_GAME_ID, nickname=nickname, sessionId=session_id)


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
    game = get_game_or_404(V1_GAME_ID, db)

    if body.startedAt is not None:
        game.started_at = body.startedAt
    if body.endedAt is not None:
        game.ended_at = body.endedAt

    db.commit()
    logger.info("게임 시간 수정 - startedAt=%s, endedAt=%s", game.started_at, game.ended_at)
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
    game = get_game_or_404(V1_GAME_ID, db)

    if game.status != GameStatus.PREGAME:
        logger.warning("단어 수정 실패 - 게임이 이미 시작됨 (status=%s)", game.status)
        raise HTTPException(status_code=409, detail="게임 시작 전에만 단어를 수정할 수 있습니다.")

    if not body.targetWord.strip():
        raise HTTPException(status_code=400, detail="요청 본문에 targetWord 필드는 필수입니다.")

    vdb = get_vector_db()
    if not vdb.word_exists(body.targetWord.strip()):
        logger.warning("단어 수정 실패 - 사전에 없는 단어: '%s'", body.targetWord.strip())
        raise HTTPException(status_code=404, detail=f"'{body.targetWord.strip()}'은(는) 사전에 없는 단어입니다.")

    logger.info("정답 단어 수정 - '%s' -> '%s'", game.target_word, body.targetWord.strip())
    game.target_word = body.targetWord.strip()
    db.commit()
    refresh_vector_similarities(game.target_word)
    return MessageResponse(message="단어가 수정되었습니다.")


# ═══════════════════════════════════════════════════════════════
# 단어 추측  POST /api/v1/games/guess
# ═══════════════════════════════════════════════════════════════
@router.post("/guess", response_model=GuessResponse)
def guess_word(
    body: GuessRequest,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    game = get_game_or_404(V1_GAME_ID, db)
    sync_game_status(game, db)

    if game.status != GameStatus.INGAME:
        raise HTTPException(status_code=409, detail="게임이 진행 중이 아닙니다.")

    word = body.word.strip()
    username = body.username.strip()
    if not word or not username:
        raise HTTPException(status_code=400, detail="요청 본문에 word와 username 필드는 필수입니다.")

    parts = authorization.split()
    session_id = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else authorization

    participant = (
        db.query(Participant)
        .filter(Participant.game_id == V1_GAME_ID, Participant.nickname == username)
        .first()
    )
    if not participant or participant.session_id != session_id:
        logger.warning("추측 인증 실패 - username=%s", username)
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    vdb = get_vector_db()
    word_data = vdb.get_word_vector(word)
    if word_data is None:
        logger.info("추측 실패 - 사전에 없는 단어: '%s' (username=%s)", word, username)
        raise HTTPException(status_code=404, detail="사전에 없는 단어입니다.")

    target_data = vdb.get_word_vector(game.target_word)
    if target_data is None:
        logger.error("정답 단어가 벡터 DB에 없음: '%s'", game.target_word)
        raise HTTPException(status_code=500, detail="정답 단어가 사전에 없는 오류가 발생했습니다.")

    w_vec, w_norm = word_data
    t_vec, t_norm = target_data
    raw_sim = vdb.cosine_similarity(w_vec, w_norm, t_vec, t_norm)
    similarity = round(max(0.0, raw_sim), 4)

    is_answer = word == game.target_word

    if similarity > participant.best_similarity:
        participant.best_similarity = similarity
        participant.closest_word = word
    if is_answer:
        participant.is_correct = True
        logger.info("정답 맞힘 - username=%s, word=%s", username, word)

    db.add(GuessHistory(
        participant_id=participant.id,
        word=word,
        similarity=similarity,
        is_answer=is_answer,
    ))
    db.commit()

    r = get_redis()
    r.zadd(f"game:{V1_GAME_ID}:leaderboard", {participant.id: participant.best_similarity})
    # r.set(f"game:{V1_GAME_ID}:closest:{participant.nickname}", participant.closest_word or word) # TODO: 최대 유사도 단어도 캐싱이 필요할 경우 주석 해제

    rank_idx = r.zrevrank(f"game:{V1_GAME_ID}:leaderboard", participant.id) # TODO: 랭킹 조회는 다른 API에서 하자.
    game_rank = (rank_idx or 0) + 1

    logger.debug("추측 결과 - username=%s, word=%s, similarity=%s, rank=%d", username, word, similarity, game_rank)
    return GuessResponse(
        label=word,
        similarity=similarity,
        rank=game_rank,
        isAnswer=is_answer,
    )


def _get_users_from_redis(game_id: int, db: Session) -> list[UserInfo]:
    """Redis leaderboard에서 참가자 목록을 랭킹 순으로 조회"""
    r = get_redis()
    entries = r.zrevrange(f"game:{game_id}:leaderboard", 0, -1, withscores=True)
    if not entries:
        return []

    participant_ids = [int(pid) for pid, _ in entries]
    participants = (
        db.query(Participant)
        .options(selectinload(Participant.guesses))
        .filter(Participant.game_id == V1_GAME_ID, Participant.id.in_(participant_ids))
        .all()
    )
    participants_by_id = {participant.id: participant for participant in participants}

    users = []
    for rank, (participant_id, score) in enumerate(entries, start=1):
        participant = participants_by_id.get(int(participant_id))
        if participant is None:
            continue

        best_guess = get_best_guess(participant)
        latest_guess = get_latest_guess(participant)

        best_submission = None
        if best_guess is not None:
            best_submission = build_submission_detail(
                best_guess.word,
                best_guess.similarity,
                best_guess.submitted_at,
            )
        elif participant.closest_word is not None:
            best_submission = build_submission_detail(
                participant.closest_word,
                participant.best_similarity,
            )

        latest_submission = None
        if latest_guess is not None:
            latest_submission = build_submission_detail(
                latest_guess.word,
                latest_guess.similarity,
                latest_guess.submitted_at,
            )

        users.append(UserInfo(
            name=participant.nickname,
            bestSimilarity=round(score, 4),
            rank=rank,
            bestSubmission=best_submission,
            latestSubmission=latest_submission,
        ))
    return users


# ═══════════════════════════════════════════════════════════════
# 게임 정보 폴링  GET /api/v1/games/polling/db
# ═══════════════════════════════════════════════════════════════
@router.get("/polling/db", response_model=GameInfoResponse)
def game_polling(db: Session = Depends(get_db)):
    game = get_game_or_404(V1_GAME_ID, db)
    sync_game_status(game, db)

    participants = (
        db.query(Participant)
        .options(selectinload(Participant.guesses))
        .filter(Participant.game_id == V1_GAME_ID)
        .order_by(Participant.best_similarity.desc())
        .all()
    )

    users = []
    for i, participant in enumerate(participants):
        best_guess = get_best_guess(participant)
        latest_guess = get_latest_guess(participant)

        best_submission = None
        if best_guess is not None:
            best_submission = build_submission_detail(
                best_guess.word,
                best_guess.similarity,
                best_guess.submitted_at,
            )
        elif participant.closest_word is not None:
            best_submission = build_submission_detail(
                participant.closest_word,
                participant.best_similarity,
            )

        latest_submission = None
        if latest_guess is not None:
            latest_submission = build_submission_detail(
                latest_guess.word,
                latest_guess.similarity,
                latest_guess.submitted_at,
            )

        users.append(UserInfo(
            name=participant.nickname,
            bestSimilarity=round(participant.best_similarity, 4),
            rank=i + 1,
            bestSubmission=best_submission,
            latestSubmission=latest_submission,
        ))

    to_unix_ms = lambda dt: int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000) if dt else None

    return GameInfoResponse(
        startAt=to_unix_ms(game.started_at),
        endAt=to_unix_ms(game.ended_at),
        users=users,
    )


# ═══════════════════════════════════════════════════════════════
# 게임 정보 폴링  GET /api/v1/games/polling
# ═══════════════════════════════════════════════════════════════
@router.get("/polling", response_model=GameInfoResponse)
def game_polling(db: Session = Depends(get_db)):
    game = get_game_or_404(V1_GAME_ID, db) # 게임 상태도 Redis에서 관리하자
    sync_game_status(game, db)

    users = _get_users_from_redis(V1_GAME_ID, db)

    to_unix_ms = lambda dt: int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000) if dt else None

    return GameInfoResponse(
        startAt=to_unix_ms(game.started_at),
        endAt=to_unix_ms(game.ended_at),
        users=users,
    )


# TODO: 무슨 결과를 조회할지 논의 필요 (참가자별 추측 기록? 전체 랭킹? 등등)
# ═══════════════════════════════════════════════════════════════
# 결과 조회  GET /api/v1/games/result
# ═══════════════════════════════════════════════════════════════
@router.get("/result", response_model=GameResultResponse)
def game_result(db: Session = Depends(get_db)):
    game = get_game_or_404(V1_GAME_ID, db)

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

    game = get_game_or_404(V1_GAME_ID, db)
    game.status = GameStatus.POSTGAME
    if not game.ended_at:
        game.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    logger.info("게임 강제 종료 - gameId=%d", V1_GAME_ID)
    return MessageResponse(message="게임이 종료되었습니다.")


# ═══════════════════════════════════════════════════════════════
# 추측 기록 조회  GET /api/v1/games/guesses
# ═══════════════════════════════════════════════════════════════
@router.get("/guesses", response_model=list[GuessHistoryItem])
def get_guess_history(
    username: str,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    parts = authorization.split()
    session_id = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else authorization

    participant = (
        db.query(Participant)
        .filter(Participant.game_id == V1_GAME_ID, Participant.nickname == username)
        .first()
    )
    if not participant or participant.session_id != session_id:
        logger.warning("추측 기록 조회 인증 실패 - username=%s", username)
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    r = get_redis()

    result = []
    for g in participant.guesses:
        if g.similarity == participant.best_similarity:
            rank_idx = r.zrevrank(f"game:{V1_GAME_ID}:leaderboard", participant.nickname)
            rank = (rank_idx or 0) + 1 if rank_idx is not None else -1
        else:
            rank = -1
        result.append(GuessHistoryItem(
            label=g.word,
            similarity=g.similarity,
            rank=rank,
            isAnswer=g.is_answer,
        ))

    return result
