import argparse
import gzip
import re
from pathlib import Path
from typing import Iterable, Set

HANGUL_REGEX = re.compile(r"^[가-힣]+$")

# 단독으로 올 수 있는 실질 품사
_SINGLE_CONTENT_TAGS = frozenset({
    "NNG",  # 일반 명사
    "NNP",  # 고유 명사
    "NNB",  # 의존 명사
    "NR",   # 수사
    "NP",   # 대명사
    "MAG",  # 일반 부사
    "MAJ",  # 접속 부사
    "MM",   # 관형사
    "IC",   # 감탄사
})

# 동사/형용사 어간 태그
_PRED_STEM_TAGS = frozenset({"VV", "VA", "VX", "VCN"})

# 파생 접미사 (하다 동사/형용사)
_DERIV_SUFFIX_TAGS = frozenset({"XSV", "XSA"})


def _load_kiwi():
    try:
        from kiwipiepy import Kiwi
        return Kiwi()
    except ImportError:
        raise ImportError("kiwipiepy가 설치되지 않았습니다: pip install kiwipiepy")


def is_base_form(word: str, kiwi) -> bool:
    """품사의 기본형인지 확인 (명사·부사 등 단독 형태소, 또는 동사/형용사 기본형 ~다)"""
    tokens = kiwi.tokenize(word)
    if not tokens:
        return False

    tags = [str(t.tag) for t in tokens]
    forms = [t.form for t in tokens]

    # 단일 실질 형태소: 행복, 갑자기, 야옹
    if len(tokens) == 1:
        return tags[0] in _SINGLE_CONTENT_TAGS

    # 동사/형용사 기본형: 어간 + 다(EF) → 기쁘다, 먹다
    if len(tokens) == 2 and tags[0] in _PRED_STEM_TAGS and tags[1] == "EF" and forms[1] == "다":
        return True

    # 파생 동사/형용사 기본형: 명사 + XSV/XSA + 다(EF) → 사랑하다, 행복하다
    if (
        len(tokens) == 3
        and tags[1] in _DERIV_SUFFIX_TAGS
        and tags[2] == "EF"
        and forms[2] == "다"
    ):
        return True

    return False


def load_hunspell_dic(dic_path: Path) -> Set[str]:
    words: Set[str] = set()
    if not dic_path.exists():
        raise FileNotFoundError(f"Hunspell dictionary file not found: {dic_path}")

    with dic_path.open("r", encoding="utf-8", errors="ignore") as f:
        header = f.readline().strip()
        try:
            expected = int(header)
        except ValueError:
            expected = None

        for line in f:
            word = line.strip().split("/")[0]
            if word:
                words.add(word)
    return words


def read_wordlist(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            token = line.strip().split()[0]
            if token:
                yield token


def read_fasttext_vocab(vec_path: Path) -> Iterable[str]:
    opener = gzip.open if vec_path.suffix == ".gz" else open
    with opener(vec_path, "rt", encoding="utf-8", errors="ignore") as f:
        header = f.readline()
        if not header or len(header.split()) != 2:
            # If there is no header, rewind and read from the first line
            f.seek(0)
        for line in f:
            parts = line.strip().split()
            if parts:
                yield parts[0]


def is_valid_korean_word(word: str) -> bool:
    return len(word) >= 1 and HANGUL_REGEX.match(word) is not None


def filter_words(
    candidates: Iterable[str],
    dictionary: Set[str] | None = None,
    blocklist: Set[str] | None = None,
    kiwi=None,
) -> list[str]:
    filtered: list[str] = []
    for word in candidates:
        if not is_valid_korean_word(word):
            continue
        if dictionary is not None and word not in dictionary:
            continue
        if blocklist is not None and any(block in word for block in blocklist):
            continue
        if kiwi is not None and not is_base_form(word, kiwi):
            continue
        filtered.append(word)
    return filtered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter Korean words from FastText vocabulary for Semantle-style answer candidates."
    )
    parser.add_argument("--vec-path", type=Path, required=True, help="Path to FastText .vec or .vec.gz file")
    parser.add_argument("--output", type=Path, required=True, help="Path to write filtered word list")
    parser.add_argument("--hunspell-dic", type=Path, help="Path to ko-aff-dic-0.7.92 dic file")
    parser.add_argument("--wordlist", type=Path, help="Optional additional word list file to intersect with")
    parser.add_argument(
        "--blocklist",
        type=Path,
        help="Optional blocklist file containing one forbidden substring per line",
    )
    parser.add_argument(
        "--use-kiwi",
        action="store_true",
        help="kiwipiepy로 품사 기본형(명사·부사·동사다·형용사다)만 허용",
    )
    args = parser.parse_args()

    dictionary = load_hunspell_dic(args.hunspell_dic) if args.hunspell_dic else None
    blocklist = set(read_wordlist(args.blocklist)) if args.blocklist else None
    kiwi = _load_kiwi() if args.use_kiwi else None

    fasttext_words = set(read_fasttext_vocab(args.vec_path))
    candidates = fasttext_words
    if args.wordlist:
        extra_words = set(read_wordlist(args.wordlist))
        candidates = fasttext_words & extra_words

    filtered = filter_words(candidates, dictionary=dictionary, blocklist=blocklist, kiwi=kiwi)
    filtered.sort()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for word in filtered:
            f.write(word + "\n")

    print(f"Filtered {len(filtered)} words and saved to {args.output}")


if __name__ == "__main__":
    main()