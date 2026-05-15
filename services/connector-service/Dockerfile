# ============================================================
# Multi-stage Dockerfile — Connector Service
# Same pattern used across all FastAPI microservices
# ============================================================

# Stage 1: dependency builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ unixodbc-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Stage 2: runtime image (minimal, non-root)
FROM python:3.11-slim AS runtime

# Install runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser

WORKDIR /app

# Copy pre-built wheels and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels

# Copy application source
COPY --chown=appuser:appuser . .

USER appuser

# Health-check uses curl (installed above)
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--workers", "2", "--log-level", "info", \
     "--access-log", "--proxy-headers"]
