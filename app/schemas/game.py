from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# ─── 게임 생성 ───────────────────────────────────────────────
class CreateGameRequest(BaseModel):
    hostname: str
    targetWord: str
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None


class CreateGameResponse(BaseModel):
    gameId: int


# ─── 게임 참가 ───────────────────────────────────────────────
class JoinGameRequest(BaseModel):
    nickname: str


class JoinGameResponse(BaseModel):
    gameId: int
    nickname: str


# ─── 게임 상태 폴링 ──────────────────────────────────────────
class GameStatusResponse(BaseModel):
    gameId: int
    gameStatus: str
    participationCount: int


# ─── 게임 시간 수정 ──────────────────────────────────────────
class UpdateEndtimeRequest(BaseModel):
    startedAt: Optional[datetime] = None
    endedAt: Optional[datetime] = None


# ─── 단어 수정 ───────────────────────────────────────────────
class UpdateWordRequest(BaseModel):
    targetWord: str


# ─── 단어 입력 ───────────────────────────────────────────────
class GuessRequest(BaseModel):
    word: str


class GuessResponse(BaseModel):
    word: str
    similarity: float
    gameRank: int
    isCorrect: bool
    bestSimilarity: float
    closestWord: str


# ─── 리더보드 ────────────────────────────────────────────────
class LeaderboardEntry(BaseModel):
    rank: int
    nickname: str
    bestSimilarity: float
    closestWord: Optional[str]


class GamePollingResponse(BaseModel):
    gameStatus: str
    participationCount: int
    leaderboard: List[LeaderboardEntry]


class LeaderboardResponse(BaseModel):
    leaderboard: List[LeaderboardEntry]


# ─── 결과 조회 ───────────────────────────────────────────────
class ParticipantResult(BaseModel):
    rank: int
    nickname: str
    bestSimilarity: float
    closestWord: Optional[str]
    isCorrect: bool


class GameResultResponse(BaseModel):
    targetWord: str
    startedAt: Optional[datetime]
    endedAt: Optional[datetime]
    participants: List[ParticipantResult]


# ─── 공통 메시지 ─────────────────────────────────────────────
class MessageResponse(BaseModel):
    message: str
