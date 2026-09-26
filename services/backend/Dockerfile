# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip uv \
    && uv pip install --system --no-cache .

# Production Runtime Stage
FROM python:3.12-slim AS runner

WORKDIR /app

# Install runtime dependencies including Tesseract OCR (eng + vie) and libpq
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-vie \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python site-packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create unprivileged user (UID 10001) for security isolation
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy application source and migrations
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini pyproject.toml ./

# Ensure storage directory exists and owned by appuser
RUN mkdir -p /app/private_storage && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/admin/readiness || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
