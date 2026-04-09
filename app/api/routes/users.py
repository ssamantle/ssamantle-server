from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import Participant
from app.schemas.user import NicknameCheckResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/check-nickname", response_model=NicknameCheckResponse)
def check_nickname(
    nickname: str = Query(..., description="확인할 닉네임"),
    db: Session = Depends(get_db),
):
    """닉네임 중복 확인 — 진행 중인 게임(WAITING/ACTIVE) 기준"""
    from app.db.models import Game
    exists = (
        db.query(Participant)
        .join(Game)
        .filter(
            Participant.nickname == nickname,
            Game.status.in_(["WAITING", "ACTIVE"]),
        )
        .first()
    )
    if exists:
        return JSONResponse(
            status_code=409,
            content={"message": "이미 사용 중인 닉네임입니다."},
        )
    return NicknameCheckResponse(isDuplicate=False)
