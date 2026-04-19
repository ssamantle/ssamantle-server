FROM python:3.12-slim AS builder

# .pyc 파일 생성 방지
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENV=production

WORKDIR /app

RUN apt-get update && \
    apt-get install -y wget && \
    wget https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.ko.300.vec.gz

COPY /scripts /app/scripts
RUN pip install --no-cache-dir -r scripts/requirements.txt

# filter_words.py 실행 (원본 FastText-test 레포에서 복사)
RUN python scripts/filter_words.py \
    --vec-path cc.ko.300.vec.gz \
    --output data/filtered_words.txt

# process_vecs.py 실행 (원본 FastText-test 레포에서 복사)
RUN python scripts/process_vecs.py \
    --vec-path cc.ko.300.vec.gz \
    --word-list data/filtered_words.txt \
    --db-path data/vectors.db

# 원본 파일을 지워 용량 확보
RUN rm cc.ko.300.vec.gz

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim

WORKDIR /app

COPY . .

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/data /app/data

# 보안을 위해 비루트 사용자 생성 및 전환
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Gunicorn + UvicornWorker 권장이지만 지금은 uvicorn을 사용하도록 함.
# worker 수는 보통 (2 x CPU 코어 수) + 1 로 설정합니다.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
