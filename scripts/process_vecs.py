import argparse
import gzip
import sqlite3
import struct
from pathlib import Path
from typing import Iterable

import numpy as np

VECTOR_DIMENSION = 300


def parse_fasttext_vectors(vec_path: Path, words: set[str]) -> Iterable[tuple[str, np.ndarray]]:
    opener = gzip.open if vec_path.suffix == ".gz" else open
    with opener(vec_path, "rt", encoding="utf-8", errors="ignore") as f:
        header = f.readline().strip().split()
        if len(header) == 2 and header[0].isdigit() and header[1].isdigit():
            pass
        else:
            f.seek(0)
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            word = parts[0]
            if word not in words:
                continue
            vector_values = list(map(float, parts[1:]))
            if len(vector_values) != VECTOR_DIMENSION:
                continue
            yield word, np.array(vector_values, dtype=np.float32)


def vector_to_blob(vec: np.ndarray) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def create_database(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vectors (word TEXT PRIMARY KEY, vec BLOB, norm REAL, sim REAL DEFAULT 0.0)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word ON vectors(word)")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(vectors)")}
    if "sim" not in columns:
        conn.execute("ALTER TABLE vectors ADD COLUMN sim REAL DEFAULT 0.0")
    return conn


def store_vectors(db_path: Path, vec_path: Path, word_list_path: Path) -> None:
    words = {line.strip() for line in word_list_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    conn = create_database(db_path)
    cursor = conn.cursor()

    for word, vec in parse_fasttext_vectors(vec_path, words):
        norm = float(np.linalg.norm(vec))
        if norm == 0.0:
            continue
        blob = vector_to_blob(vec)
        cursor.execute(
            "INSERT OR REPLACE INTO vectors (word, vec, norm, sim) VALUES (?, ?, ?, ?)",
            (word, blob, norm, 0.0),
        )

    conn.commit()
    conn.close()
    print(f"Stored vectors for {len(words)} candidate words into {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process FastText vectors and store filtered word embeddings into SQLite."
    )
    parser.add_argument("--vec-path", type=Path, required=True, help="Path to FastText .vec or .vec.gz file")
    parser.add_argument("--word-list", type=Path, required=True, help="Path to filtered word list")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to SQLite database file")
    args = parser.parse_args()
    args.db_path.parent.mkdir(parents=True, exist_ok=True)
    store_vectors(args.db_path, args.vec_path, args.word_list)


if __name__ == "__main__":
    main()