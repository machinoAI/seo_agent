# syntax=docker/dockerfile:1

# ---- build: install the package into an isolated virtualenv ----------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Optional extras, e.g. --build-arg EXTRAS="[postgres]" for the PostgreSQL driver
ARG EXTRAS=""

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".${EXTRAS}"

# ---- runtime: slim image, non-root user, no build tooling -------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/output \
    && chown -R app:app /app/data
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
