from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.database import Base
from app.db.enums import GameStatus


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String, nullable=False)
    host_session_id = Column(String, nullable=False)
    target_word = Column(String, nullable=False)
    status = Column(String, default=GameStatus.PREGAME)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    participants = relationship("Participant", back_populates="game")


class Participant(Base):
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    nickname = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    best_similarity = Column(Float, default=0.0)
    closest_word = Column(String, nullable=True)
    is_correct = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    game = relationship("Game", back_populates="participants")
