from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Game, Participant

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/validate")
def validate_token(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """세션ID(토큰) 유효성 검사"""
    parts = authorization.split()
    session_id = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else authorization

    is_host = db.query(Game).filter(Game.host_session_id == session_id).first() is not None
    is_participant = db.query(Participant).filter(Participant.session_id == session_id).first() is not None

    return is_host or is_participant
