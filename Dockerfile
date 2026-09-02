FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY rxguard ./rxguard
COPY web ./web
RUN pip install --no-cache-dir .

EXPOSE 8094
CMD ["python", "-m", "rxguard.api"]

