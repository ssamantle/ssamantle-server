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
    sessionId: str


# ─── 게임 참가 ───────────────────────────────────────────────
class JoinGameRequest(BaseModel):
    nickname: str


class JoinGameResponse(BaseModel):
    gameId: int
    nickname: str
    sessionId: str


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
    username: str
    word: str


class GuessResponse(BaseModel):
    label: str
    similarity: float
    rank: int
    isAnswer: bool


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


# ─── v1 추측 기록 ────────────────────────────────────────────
class GuessHistoryRequest(BaseModel):
    username: str


class GuessHistoryItem(BaseModel):
    label: str
    similarity: float
    rank: int
    isAnswer: bool


# ─── v1 게임 정보 폴링 ───────────────────────────────────────
class UserInfo(BaseModel):
    name: str
    bestSimilarity: float
    rank: int


class GameInfoResponse(BaseModel):
    startAt: Optional[int]   # Unix ms
    endAt: Optional[int]     # Unix ms
    users: List[UserInfo]


# ─── 공통 메시지 ─────────────────────────────────────────────
class MessageResponse(BaseModel):
    message: str
