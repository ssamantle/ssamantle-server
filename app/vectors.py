import sqlite3
import struct
from pathlib import Path
from typing import Iterator, Optional, Tuple

import numpy as np

VECTOR_DIMENSION = 300


class VectorDB:
    """FastText 벡터 데이터베이스 관리 클래스"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_db_exists()
        self._ensure_similarity_column()

    def _ensure_db_exists(self):
        """데이터베이스 파일이 존재하는지 확인"""
        if not self.db_path.exists():
            raise FileNotFoundError(f"Vector database not found: {self.db_path}")

    def _unpack_vector(self, vec_blob: bytes) -> np.ndarray:
        return np.array(
            struct.unpack(f"<{VECTOR_DIMENSION}f", vec_blob),
            dtype=np.float32,
        )

    def _ensure_similarity_column(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS vectors (word TEXT PRIMARY KEY, vec BLOB, norm REAL, sim REAL DEFAULT 0.0)"
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(vectors)")}
            if "sim" not in columns:
                conn.execute("ALTER TABLE vectors ADD COLUMN sim REAL DEFAULT 0.0")
                conn.commit()

    def _iter_vectors(self, conn: sqlite3.Connection, batch_size: int) -> Iterator[list[tuple[str, bytes, float]]]:
        cursor = conn.execute("SELECT word, vec, norm FROM vectors")
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            yield rows

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
                vec = self._unpack_vector(vec_blob)
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

    def update_similarities(self, target_word: str, batch_size: int = 1000) -> int:
        """정답 단어 기준으로 모든 row의 sim 값을 배치 갱신"""
        target_vector = self.get_word_vector(target_word)
        if target_vector is None:
            raise ValueError(f"Target word not found: {target_word}")

        target_vec, target_norm = target_vector
        updated_rows = 0

        with sqlite3.connect(self.db_path) as conn:
            update_cursor = conn.cursor()

            for rows in self._iter_vectors(conn, batch_size):
                updates: list[tuple[float, str]] = []
                for word, vec_blob, norm in rows:
                    vec = self._unpack_vector(vec_blob)
                    similarity = self.cosine_similarity(vec, float(norm), target_vec, target_norm)
                    updates.append((similarity, word))

                update_cursor.executemany(
                    "UPDATE vectors SET sim = ? WHERE word = ?",
                    updates,
                )
                updated_rows += len(updates)

            conn.commit()

        return updated_rows