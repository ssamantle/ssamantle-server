import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Dict, Optional


class SecretsManager:
    """날짜별 정답 단어 관리 클래스"""

    def __init__(self, secrets_path: Path, words_path: Path):
        self.secrets_path = secrets_path
        self.words_path = words_path
        self._secrets_cache: Optional[Dict] = None

    def _load_secrets(self) -> Dict:
        """시크릿 파일 로드 (캐싱)"""
        if self._secrets_cache is None:
            if not self.secrets_path.exists():
                raise FileNotFoundError(f"Secrets file not found: {self.secrets_path}")

            with open(self.secrets_path, 'r', encoding='utf-8') as f:
                self._secrets_cache = json.load(f)

        return self._secrets_cache

    def _load_words(self) -> list[str]:
        """단어 목록 로드"""
        if not self.words_path.exists():
            raise FileNotFoundError(f"Words file not found: {self.words_path}")

        with open(self.words_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]

    def get_secret_word(self, target_date: date) -> str:
        """특정 날짜의 정답 단어 조회"""
        words = self._load_words()
        if not words:
            raise ValueError("No words available")

        # 날짜를 기반으로 단어 선택 (결정론적)
        return self._pick_word_for_date(words, target_date)

    def _pick_word_for_date(self, words: list[str], target_date: date, salt: str = "semantle-ko") -> str:
        """날짜를 기반으로 단어 선택 (결정론적)"""
        seed = f"{target_date.isoformat()}|{salt}"
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % len(words)
        return words[index]

    def verify_secret_token(self, token: str, target_date: date) -> bool:
        """시크릿 토큰 검증"""
        secrets = self._load_secrets()
        date_str = target_date.isoformat()

        if date_str not in secrets:
            return False

        expected_token = secrets[date_str]["token"]
        return token == expected_token

    def get_today_secret_word(self) -> str:
        """오늘의 정답 단어 조회"""
        return self.get_secret_word(date.today())