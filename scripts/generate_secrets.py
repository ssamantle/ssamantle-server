import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Sequence


def load_word_list(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pick_word_for_date(words: Sequence[str], target_date: date, salt: str = "semantle-ko") -> str:
    seed = f"{target_date.isoformat()}|{salt}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % len(words)
    return words[index]


def secret_token(secret: str, target_date: date, salt: str = "semantle-ko") -> str:
    payload = f"{target_date.isoformat()}|{secret}|{salt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def generate_secrets(words: list[str], year: int, output: Path) -> None:
    target_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    payload: dict[str, dict[str, str]] = {}
    current = target_date
    while current <= end_date:
        secret_word = pick_word_for_date(words, current)
        payload[current.isoformat()] = {
            "token": secret_token(secret_word, current),
            "secret_hash": hashlib.sha256(secret_word.encode("utf-8")).hexdigest(),
        }
        current = current.toordinal() + 1
        current = date.fromordinal(current)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated secrets for {year} into {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic daily secret tokens from a filtered word list.")
    parser.add_argument("--word-list", type=Path, required=True, help="Path to filtered word list")
    parser.add_argument("--year", type=int, required=True, help="Year to generate secrets for")
    parser.add_argument("--output", type=Path, required=True, help="Path to JSON output file")
    args = parser.parse_args()

    words = load_word_list(args.word_list)
    if not words:
        raise ValueError("The filtered word list is empty.")
    generate_secrets(words, args.year, args.output)


if __name__ == "__main__":
    main()