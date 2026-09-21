FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*

COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
RUN pip install --no-cache-dir --upgrade pip uv && uv sync --frozen --no-dev
COPY apps/api/app ./app
# The seeded demo remains a real repository fixture, not injected evaluation data.
COPY demo-repos /demo-repos
ENV PLANPROOF_FIXTURES_ROOT=/demo-repos

RUN useradd --create-home --uid 10001 planproof
USER planproof
EXPOSE 8080
CMD ["sh", "-c", ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
