import logging
import sqlite3
import struct
from pathlib import Path
from typing import Iterator, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

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
        """sim, rank 컬럼이 없는 구버전 DB를 위한 마이그레이션"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS vectors (word TEXT PRIMARY KEY, vec BLOB, norm REAL, sim REAL DEFAULT 0.0)"
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(vectors)")}
            if "sim" not in columns:
                conn.execute("ALTER TABLE vectors ADD COLUMN sim REAL DEFAULT 0.0")
            if "rank" not in columns:
                conn.execute("ALTER TABLE vectors ADD COLUMN rank INTEGER DEFAULT 0")
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
        """정답 단어 기준으로 모든 단어의 sim과 rank를 갱신한다.
        게임 생성 또는 정답 단어 변경 시 1회 호출된다."""
        target_vector = self.get_word_vector(target_word)
        if target_vector is None:
            raise ValueError(f"Target word not found: {target_word}")

        target_vec, target_norm = target_vector
        updated_rows = 0

        with sqlite3.connect(self.db_path) as conn:
            update_cursor = conn.cursor()

            # 1단계: 전체 단어의 코사인 유사도를 배치로 갱신
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

            # 2단계: 전체 단어에 유사도 내림차순으로 순위 부여
            all_words = update_cursor.execute(
                "SELECT word FROM vectors ORDER BY sim DESC"
            ).fetchall()
            rank_updates = [(i + 1, word) for i, (word,) in enumerate(all_words)]
            update_cursor.executemany(
                "UPDATE vectors SET rank = ? WHERE word = ?",
                rank_updates,
            )

            conn.commit()

        logger.info(
            "유사도·순위 갱신 완료 — target=%s, total=%d, ranked=%d",
            target_word, updated_rows, len(rank_updates),
        )
        return updated_rows

    def get_word_rank(self, word: str) -> int:
        """단어의 정답 유사도 순위를 반환한다. 단어가 없으면 0을 반환한다."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT rank FROM vectors WHERE word = ?", (word,)
                ).fetchone()
                return int(row[0]) if row else 0
        except sqlite3.Error as e:
            logger.error("rank 조회 실패 — word=%s, error=%s", word, e)
            return 0

    def get_word_similarity_and_rank(self, word: str) -> Optional[Tuple[float, int]]:
        """사전 계산된 유사도와 순위를 반환한다. 단어가 없으면 None을 반환한다."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT sim, rank FROM vectors WHERE word = ?", (word,)
                ).fetchone()
                if row is None:
                    return None
                return float(row[0]), int(row[1])
        except sqlite3.Error as e:
            logger.error("유사도·순위 조회 실패 — word=%s, error=%s", word, e)
            return None