from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
from app.vectors import VectorDB
from app.config import get_settings

# 설정 로드
settings = get_settings()

# 벡터 DB 초기화 (파일이 있으면)
vector_db = None

try:
    vector_db = VectorDB(Path(settings.vector_db_path))
except FileNotFoundError:
    print("Warning: Vector database not found. Similarity features will not be available.")

router = APIRouter(prefix="/api/similarity", tags=["similarity"])


class SimilarityRequest(BaseModel):
    """두 단어 유사도 계산 요청"""
    word1: str
    word2: str


class SimilarityResponse(BaseModel):
    """유사도 계산 응답"""
    word1: str
    word2: str
    similarity: int  # -100 ~ 100 범위


class GuessRequest(BaseModel):
    """정답 추측 요청"""
    game_id: int
    word: str


class GuessResponse(BaseModel):
    """정답 추측 응답"""
    game_id: int
    guess: str
    similarity: int


# @router.post("/", response_model=SimilarityResponse)
# async def calculate_similarity(request: SimilarityRequest):
#     """두 단어의 유사도를 계산합니다."""
#     if vector_db is None:
#         raise HTTPException(
#             status_code=503,
#             detail="Vector database not available. Please set up the data files first."
#         )
#
#     word1, word2 = request.word1.strip(), request.word2.strip()
#
#     if not word1 or not word2:
#         raise HTTPException(status_code=400, detail="Both words are required")
#
#     data1 = vector_db.get_word_vector(word1)
#     data2 = vector_db.get_word_vector(word2)
#
#     if data1 is None or data2 is None:
#         missing = []
#         if data1 is None:
#             missing.append(word1)
#         if data2 is None:
#             missing.append(word2)
#         raise HTTPException(
#             status_code=404,
#             detail=f"Word(s) not found in vector database: {', '.join(missing)}"
#         )
#
#     vec1, norm1 = data1
#     vec2, norm2 = data2
#     score = vector_db.cosine_similarity(vec1, norm1, vec2, norm2)
#     scaled_score = vector_db.scaled_similarity(score)
#
#     return SimilarityResponse(
#         word1=word1,
#         word2=word2,
#         similarity=scaled_score
#     )


# @router.post("/guess", response_model=GuessResponse)
# async def guess_secret_word(request: GuessRequest, db: Session = Depends(get_db)):
#     """정답 단어를 추측합니다."""
#     if vector_db is None:
#         raise HTTPException(
#             status_code=503,
#             detail="Vector database not available. Please set up the data files first."
#         )
#
#     guess_word = request.word.strip()
#     if not guess_word:
#         raise HTTPException(status_code=400, detail="Guess word is required")
#
#     game = db.query(Game).filter(Game.id == request.game_id).first()
#     if not game:
#         raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다.")
#
#     secret_word = game.target_word
#
#     guess_data = vector_db.get_word_vector(guess_word)
#     if guess_data is None:
#         raise HTTPException(
#             status_code=404,
#             detail=f"Guess word not found in vector database: {guess_word}"
#         )
#
#     secret_data = vector_db.get_word_vector(secret_word)
#     if secret_data is None:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Secret word not found in vector database: {secret_word}"
#         )
#
#     guess_vec, guess_norm = guess_data
#     secret_vec, secret_norm = secret_data
#     score = vector_db.cosine_similarity(guess_vec, guess_norm, secret_vec, secret_norm)
#     scaled_score = vector_db.scaled_similarity(score)
#
#     return GuessResponse(
#         game_id=request.game_id,
#         guess=guess_word,
#         similarity=scaled_score
#     )