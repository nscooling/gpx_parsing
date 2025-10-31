# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5050

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure runtime upload directory exists
RUN mkdir -p uploads

EXPOSE 5050

CMD ["sh", "-c", "gunicorn --timeout ${GUNICORN_TIMEOUT:-180} --bind 0.0.0.0:${PORT:-5050} app:app"]
