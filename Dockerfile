FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "cd /app/backend && alembic upgrade head && cd /app && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
