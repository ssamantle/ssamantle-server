# semantle-server

FastAPI 기반 백엔드 서비스 - 한국어 유사도 게임 서버

## 🚀 설정 및 실행 가이드

### 1. 가상환경 활성화

**Windows (PowerShell)**
```bash
.\venv\Scripts\Activate.ps1
```

**Windows (CMD)**
```bash
.\venv\Scripts\activate.bat
```

**macOS/Linux**
```bash
source venv/bin/activate
```

### 2. 패키지 설치

가상환경 활성화 후:
```bash
pip install -r requirements.txt
```

### 3. 서버 실행

**개발 모드 (자동 리로드 활성화)**
```bash
python main.py
```

또는 uvicorn 직접 실행:
```bash
uvicorn main:app --reload
```

**프로덕션 모드**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. API 문서 확인

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📁 프로젝트 구조

```
semantle-server/
├── venv/                    ← 가상환경 (Python 격리 환경)
├── data/                    ← FastText 데이터 파일들
│   ├── vectors.db          ← 벡터 데이터베이스
│   ├── filtered_words.txt  ← 필터링된 단어 목록
│   └── daily_secrets_2026.json ← 날짜별 정답 단어
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── items.py    ← 아이템 API
│   │       ├── health.py   ← 헬스체크 API
│   │       └── similarity.py ← 유사도 계산 API ⭐
│   ├── models/             ← 데이터베이스 모델
│   ├── schemas/            ← Pydantic 스키마
│   ├── vectors.py          ← 벡터 DB 관리 ⭐
│   ├── secrets.py          ← 정답 단어 관리 ⭐
│   └── config.py           ← 설정 관리
├── main.py                 ← 서버 시작점
├── requirements.txt        ← 패키지 목록
├── .env                    ← 환경 변수
├── .gitignore              ← git 제외 파일
└── README.md               ← 프로젝트 설명서
```

## ⚙️ FastText 데이터 준비 (꼬맨틀 기능용)

꼬맨틀 게임 기능을 사용하려면 FastText 벡터 데이터를 준비해야 합니다.

### 1. 데이터 파일 다운로드

```bash
# FastText 한국어 벡터 다운로드 (Meta에서 제공)
wget https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.ko.300.vec.gz

# 한국어 맞춤법 사전 다운로드 (선택사항)
wget https://github.com/spellcheck-ko/hunspell-dict-ko/raw/master/ko-aff-dic-0.7.92.dic
```

### 2. 단어 필터링

```bash
# filter_words.py 실행 (원본 FastText-test 레포에서 복사)
python scripts/filter_words.py --vec-path cc.ko.300.vec.gz \
  --output data/filtered_words.txt \
  --use-kiwi
  # --hunspell-dic ko-aff-dic-0.7.92.dic
```

### 3. 벡터 DB 생성

```bash
# process_vecs.py 실행 (원본 FastText-test 레포에서 복사)
python scripts/process_vecs.py --vec-path cc.ko.300.vec.gz \
  --word-list data/filtered_words.txt \
  --db-path data/vectors.db
```

### 4. 정답 단어 생성

```bash
# generate_secrets.py 실행 (원본 FastText-test 레포에서 복사)
# 선택사항
python scripts/generate_secrets.py --word-list data/filtered_words.txt \
  --year 2026 \
  --output data/daily_secrets_2026.json
```

## 📝 API 엔드포인트

### 기본 API
- `GET /` - 서버 상태 확인
- `GET /health` - 헬스 체크

### 유사도 API ⭐
- `POST /api/similarity/` - 두 단어 유사도 계산
- `POST /api/similarity/guess` - 정답 단어 추측

### 예시 요청

```bash
# 유사도 계산
curl -X POST http://localhost:8000/api/similarity/ \
  -H "Content-Type: application/json" \
  -d '{"word1": "사랑", "word2": "행복"}'

# 정답 추측
curl -X POST http://localhost:8000/api/similarity/guess \
  -H "Content-Type: application/json" \
  -d '{"word": "사랑", "date": "2026-04-08"}'
```

## 🔧 환경 변수 설정

`.env` 파일에서 다음을 설정할 수 있습니다:

```
ENVIRONMENT=development
DEBUG=True
HOST=0.0.0.0
PORT=8000

# FastText 데이터 경로
VECTOR_DB_PATH=data/vectors.db
WORDS_LIST_PATH=data/filtered_words.txt
SECRETS_PATH=data/daily_secrets_2026.json
```

## 💡 주요 파일 설명

- **main.py**: 🚀 서버 시작점 - 여기서 실행함
- **app/api/routes/similarity.py**: ⭐ 유사도 계산 API
- **app/vectors.py**: ⭐ FastText 벡터 DB 관리
- **app/secrets.py**: ⭐ 날짜별 정답 단어 관리
- **app/config.py**: ⚙️ 환경 설정 - .env 읽음
- **data/**: 📊 FastText 벡터 데이터 저장소

## 🎯 다음 단계

1. FastText 벡터 파일 다운로드
2. 데이터 전처리 스크립트 실행
3. 유사도 API 테스트
4. 프론트엔드 연동
5. 배포 설정
