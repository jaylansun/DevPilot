FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    UV_SYSTEM_CERTS=true \
    UV_HTTP_RETRIES=10 \
    UV_HTTP_CONNECT_TIMEOUT=30 \
    UV_HTTP_TIMEOUT=60 \
    UV_LINK_MODE=copy

# 仅安装一次 uv；项目依赖在下方根据锁文件安装。
RUN pip install --no-cache-dir uv==0.12.10

WORKDIR /app

# 先复制依赖描述文件，使仅修改应用代码时可以复用该镜像层。
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM base AS test

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --group dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY tests ./tests

CMD ["pytest", "-q"]

FROM base AS runtime

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
