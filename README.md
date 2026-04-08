# semantle-server

FastAPI 기반 백엔드 서비스

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
├── app/
│   ├── api/
│   │   └── routes/          # API 엔드포인트
│   │       ├── items.py
│   │       └── health.py
│   ├── models/              # 데이터 모델 (DB 모델)
│   ├── schemas/             # Pydantic 스키마 (요청/응답)
│   │   └── item.py
│   └── config.py            # 애플리케이션 설정
├── main.py                  # 애플리케이션 진입점
├── requirements.txt         # 패키지 목록
├── .env                     # 환경 변수
├── .env.example             # 환경 변수 예제
└── .gitignore               # git 무시 파일
```

## ⚙️ 환경 변수 설정

`.env` 파일에서 다음을 설정할 수 있습니다:

```
ENV=development
DEBUG=True
HOST=0.0.0.0
PORT=8000
```

## 📝 주요 파일 설명

- **main.py**: FastAPI 앱 인스턴스 생성 및 라우터 등록
- **app/config.py**: 환경 설정 관리 (Settings 클래스)
- **app/api/routes/**: API 엔드포인트 정의
- **app/schemas/**: Pydantic 데이터 모델 (직렬화/검증)
- **app/models/**: SQLAlchemy 등의 DB 모델 (필요시)

## 🔧 새로운 엔드포인트 추가 방법

1. `app/api/routes/` 디렉토리에 새 파일 생성
2. APIRouter 인스턴스 생성 및 엔드포인트 정의
3. `main.py`에서 `app.include_router()` 호출

예시:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/example", tags=["example"])

@router.get("/")
async def get_example():
    return {"message": "Hello"}
```

## 🗄️ 데이터베이스 연결 (선택사항)

데이터베이스가 필요한 경우:
```bash
pip install sqlalchemy psycopg2-binary  # PostgreSQL의 경우
```

그 후 `app/database.py` 파일을 생성하여 DB 연결 설정

## 📌 유용한 명령어

가상환경 비활성화:
```bash
deactivate
```

requirements.txt 업데이트:
```bash
pip freeze > requirements.txt
```

## 🎯 다음 단계

1. `.env.example` 파일 생성 (민감한 정보 제외)
2. 데이터베이스 연결 설정 (필요시)
3. 인증/인가 추가 (필요시)
4. 테스트 코드 작성
5. 배포 설정
