# One image for the whole app (B12, #34): the API and the built frontend on one port, with the search index built in.
#
# Build the index first, then the image (the README has the steps; frontend/e2e/container.sh does both and checks
# the result):
#   cd backend && EMBEDDER=hash INDEX_PATH=data/index-image uv run python -m app.rag.build_index && cd ..
#   docker build -t patch .
#   docker run --rm -p 8080:8080 patch          # http://localhost:8080
#
# No key and no .env go in: settings come from environment variables at `docker run` (or Cloud Run's settings).
# The image records the embedder its index was built with (EMBEDDER, EMBED_MODEL). Run it with another one and it
# stops at start-up with the index-mismatch error, as it does outside the container.

# --- 1. The frontend: npm run build writes frontend/dist. The API is under /api on the same port.
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN VITE_API_URL=/api npm run build

# --- 2. The API: Python with the locked dependencies, the snapshot, the index and the built frontend.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/app ./app
COPY backend/fixtures ./fixtures
# The Dev page's model-check report reads the design tokens from the frontend's source
COPY frontend/src/styles/tokens.css /app/frontend/src/styles/tokens.css
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# The search index, built before the image by app/rag/build_index.py. Its embedder is recorded below.
ARG INDEX_DIR=backend/data/index-image
ARG EMBEDDER=hash
ARG EMBED_MODEL=
COPY ${INDEX_DIR} /app/index

RUN useradd --create-home --uid 10001 patch && mkdir -p /app/backend/data && chown -R patch /app/backend/data /app/index
USER patch

ENV EMBEDDER=${EMBEDDER} EMBED_MODEL=${EMBED_MODEL} INDEX_PATH=/app/index FRONTEND_DIR=/app/frontend/dist \
    STATE_PATH=/app/backend/data/state.json PATH=/app/backend/.venv/bin:$PATH PORT=8080
EXPOSE 8080
# Cloud Run sets PORT; 8080 otherwise
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
