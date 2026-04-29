# semantle-server

FastAPI 기반 한국어 단어 유사도 게임(Semantle) 백엔드 서버

> 현재 **V1** 기준으로 구현되어 있습니다. V1 리팩토링 후 V2로 전환 예정입니다.

---

## V1 현황 및 TODO

### As-Is (구현 완료)

- 기본 Semantle 게임 기능 구현
- 실시간 멀티플레이 요소 추가
- 커스텀 사용자명으로 게임에 참가
- 지정된 시간에 동시 시작 및 종료
- 정답 단어 별도 지정 기능
- 레이스 맵 (실시간 리더보드) 기능
- 정답 시 Confetti 애니메이션 재생

### TODO

**기능 / 운영**
- [ ] Server API 별 Throughput 측정
- [ ] Redis RDB Cache Hit Rate 개선
- [ ] MSA 적용 — 임베딩 작업(`update_similarities`)을 별도 서비스로 분리, 서비스 간 통신은 REST API
- [ ] HTTPS 호스팅 선택지 제공
- [ ] 하위 호환성 유지 — Client에 전파되는 변경사항 없도록 관리
- [ ] i18n — 시간 표기를 Korea Time Zone(KST, UTC+9) 기준으로 통일

**버그 / 기술 부채**
- [ ] SQLite + 4 workers 동시 쓰기 충돌 — `update_similarities()` 실행 중 다른 워커의 읽기 요청에서 `database is locked` 에러 발생 가능. 프로덕션은 PostgreSQL + 벡터 DB 분리 필요
- [ ] `gameRank` 하드코딩 수정 — 추측 응답의 `rank` 필드가 하드코딩 `1`로 반환됨
- [ ] `update_similarities()` HTTP 요청 블로킹 — 게임 생성/단어 변경 시 ~10만 단어 일괄 업데이트가 동기 실행되어 응답 지연 발생. `BackgroundTasks`로 분리 필요
- [ ] `/result` 엔드포인트 상태 가드 누락 — INGAME 중에도 결과 조회 가능
- [ ] V0 레거시 코드 제거 — `app/api/routes/` 폴더가 `main.py`에 등록되지 않은 채 잔존
- [ ] 시간대 혼용 — 일부 코드는 KST, 일부는 UTC 사용. `started_at`/`ended_at` 비교 로직에서 오차 가능성
- [ ] CORS 전체 허용 (`"*"`) — 프로덕션에서 실제 프론트엔드 도메인으로 제한 필요
- [ ] `/guess` Rate Limiting 없음 — 단어 무제한 제출 가능
- [ ] 테스트 없음 — 유사도 계산, 게임 상태 전환, 인증 로직 전반에 테스트 부재

---

## 프로젝트 구조

```
semantle-server/
├── app/
│   ├── api/
│   │   ├── v1/                   ← 현재 사용 중인 API
│   │   │   ├── games.py          ← 게임 API (단일 게임, V1_GAME_ID=1)
│   │   │   └── auth.py           ← 토큰 검증
│   │   └── routes/               ← 레거시 V0 (비활성)
│   │       ├── games.py
│   │       ├── health.py
│   │       └── users.py
│   ├── db/
│   │   ├── models.py             ← Game, Participant, GuessHistory
│   │   ├── database.py           ← SQLAlchemy 엔진/세션
│   │   └── enums.py              ← GameStatus (PREGAME/INGAME/POSTGAME)
│   ├── schemas/
│   │   └── game.py               ← Pydantic 요청/응답 스키마
│   ├── utils/
│   │   ├── __init__.py           ← VectorDB, Redis, 게임 헬퍼
│   │   └── logging.py            ← 구조화 로깅
│   ├── vectors.py                ← VectorDB 클래스 (FastText SQLite)
│   └── config.py                 ← 설정 관리
├── data/
│   ├── vectors.db                ← 단어 벡터 SQLite DB (40MB)
│   ├── filtered_words.txt        ← 필터링된 한국어 단어 목록
│   └── daily_secrets_2026.json   ← 날짜별 정답 단어
├── scripts/
│   ├── filter_words.py           ← FastText 어휘 필터링
│   ├── process_vecs.py           ← vectors.db 생성
│   ├── generate_secrets.py       ← 날짜별 정답 단어 생성
│   └── requirements.txt          ← 스크립트 전용 의존성
├── main.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env
```

---

## 실행 방법

### 로컬 개발 환경

**1. 가상환경 활성화 및 패키지 설치**

```bash
# macOS/Linux
source venv/bin/activate

# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
```

**2. 벡터 데이터 준비** (최초 1회, `data/vectors.db`가 없는 경우)

```bash
# FastText 한국어 벡터 다운로드 (Meta 제공, ~2GB)
wget https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.ko.300.vec.gz

# Hunspell 한국어 사전 다운로드
wget -O ko-aff-dic.zip https://github.com/spellcheck-ko/hunspell-dict-ko/releases/download/0.7.92/ko-aff-dic-0.7.92.zip
mkdir -p data && unzip ko-aff-dic.zip "*.dic" -d data/
mv data/ko-aff-dic-0.7.92/ko.dic data/ko.dic

# 단어 필터링 (한국어 실질 형태소만 추출)
python scripts/filter_words.py \
  --vec-path cc.ko.300.vec.gz \
  --output data/filtered_words.txt \
  --hunspell-dic data/ko.dic \
  --use-kiwi

# 벡터 DB 생성
python scripts/process_vecs.py \
  --vec-path cc.ko.300.vec.gz \
  --word-list data/filtered_words.txt \
  --db-path data/vectors.db
```

**3. 서버 실행**

```bash
# 개발 모드 (자동 리로드)
python main.py

# 또는 uvicorn 직접
uvicorn main:app --reload
```

---

### Docker (프로덕션)

Docker 이미지 빌드 시 데이터 파일 다운로드 및 전처리가 자동으로 실행됩니다. 별도의 데이터 준비가 필요 없습니다.

```bash
docker-compose up -d
```

서비스 구성:

| 서비스 | 이미지 | 포트 |
|--------|--------|------|
| server | ssamantle-server:dev | 8000 |
| postgres | postgres:16 | 5432 |
| redis | redis:latest | 6379 |

데이터는 Docker named volume(`server_data`, `postgres_data`, `redis_data`)에 영속 저장됩니다.

---

## 환경 변수

`.env` 파일로 설정합니다.

```dotenv
ENVIRONMENT=development
DEBUG=True
HOST=0.0.0.0
PORT=8000

# 데이터베이스 (로컬: SQLite, 프로덕션: PostgreSQL)
DATABASE_URL=sqlite:///./data/semantle.db

# Redis
REDIS_URL=redis://localhost:6380/0

# 세션 서명 키 (프로덕션에서 반드시 변경)
SECRET_KEY=dev-secret-key-change-in-production

# 데이터 파일 경로
VECTOR_DB_PATH=data/vectors.db
WORDS_LIST_PATH=data/filtered_words.txt
SECRETS_PATH=data/daily_secrets_2026.json
```

Docker 환경에서는 `docker-compose.yml`의 `environment` 블록이 PostgreSQL/Redis 호스트를 자동으로 덮어씁니다.

---

## API 엔드포인트 (V1)

### 기본

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/` | 서버 상태 확인 |
| `GET` | `/health` | 헬스 체크 |
| `GET` | `/auth/validate` | Bearer 토큰 유효성 검증 |

### 게임 (`/api/v1/games`)

| 메서드 | 경로 | 권한 | 설명 |
|--------|------|------|------|
| `POST` | `/api/v1/games` | 호스트 | 게임 생성 |
| `POST` | `/api/v1/games/join` | - | 게임 참가 |
| `PATCH` | `/api/v1/games/word` | 호스트 | 정답 단어 변경 (PREGAME만) |
| `PATCH` | `/api/v1/games/time` | 호스트 | 게임 시간 설정 |
| `POST` | `/api/v1/games/guess` | 참가자 | 단어 추측 제출 |
| `GET` | `/api/v1/games/polling` | - | 실시간 게임 상태 조회 (Redis) |
| `GET` | `/api/v1/games/result` | - | 최종 결과 조회 |
| `POST` | `/api/v1/games/end` | 호스트 | 게임 강제 종료 |
| `GET` | `/api/v1/games/guesses` | 참가자 | 내 추측 기록 조회 |

API 문서: `http://localhost:8000/docs`

---

## 데이터 파일 설명

| 파일 | 역할 |
|------|------|
| `cc.ko.300.vec.gz` | Meta FastText 한국어 학습 결과물. 단어별 300차원 벡터 룩업 테이블 (~2GB). 전처리 후 삭제해도 무방. |
| `data/ko.dic` | Hunspell 한국어 사전. `filter_words.py` 전처리 단계에서만 사용. |
| `data/filtered_words.txt` | FastText 어휘와 ko.dic의 교집합에서 실질 형태소만 추린 단어 목록. |
| `data/vectors.db` | `filtered_words.txt` 단어들의 벡터를 SQLite 바이너리로 저장한 DB. 런타임에서 사용. |
| `data/daily_secrets_2026.json` | 날짜별 정답 단어 목록 (현재 API에서 미사용). |
