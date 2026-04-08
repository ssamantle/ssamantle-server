import sqlite3
import struct
from pathlib import Path
from typing import Tuple, Optional
import numpy as np

VECTOR_DIMENSION = 300


class VectorDB:
    """FastText 벡터 데이터베이스 관리 클래스"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """데이터베이스 파일이 존재하는지 확인"""
        if not self.db_path.exists():
            raise FileNotFoundError(f"Vector database not found: {self.db_path}")

    def get_word_vector(self, word: str) -> Optional[Tuple[np.ndarray, float]]:
        """단어의 벡터와 노름(norm)을 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT vec, norm FROM vectors WHERE word = ?",
                    (word,)
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                # BLOB에서 벡터 복원
                vec_blob, norm = row
                vec = np.array(
                    struct.unpack(f"<{VECTOR_DIMENSION}f", vec_blob),
                    dtype=np.float32
                )
                return vec, float(norm)
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return None

    def cosine_similarity(self, vec1: np.ndarray, norm1: float,
                         vec2: np.ndarray, norm2: float) -> float:
        """두 벡터의 코사인 유사도를 계산"""
        if norm1 == 0 or norm2 == 0:
            return 0.0

        # 코사인 유사도 계산
        score = float(np.dot(vec1, vec2) / (norm1 * norm2))

        # -1.0 ~ 1.0 범위로 클램핑
        return max(-1.0, min(1.0, score))

    def scaled_similarity(self, score: float) -> int:
        """유사도를 -100 ~ 100 범위로 스케일링"""
        return int(round(score * 100))

    def word_exists(self, word: str) -> bool:
        """단어가 데이터베이스에 존재하는지 확인"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM vectors WHERE word = ? LIMIT 1",
                    (word,)
                )
                return cursor.fetchone() is not None
        except sqlite3.Error:
            return False