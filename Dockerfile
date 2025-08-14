# Python 3.10을 기반으로 하는 경량 이미지
FROM python:3.10-slim

# 환경변수: Python이 .pyc 생성 안 하게 + stdout 버퍼링 해제
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 작업 디렉토리 설정
WORKDIR /app

# 필요 파일 복사
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 프로젝트 전체 복사
COPY . .

# .env가 docker-compose에서 주입되므로 별도 처리 없음

# 포트 오픈
EXPOSE 5000

# Flask 앱 실행
CMD ["python", "app.py"]
