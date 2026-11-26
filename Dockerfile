FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /srv/combinellm
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-python-downloads

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/srv/combinellm/.venv/bin:$PATH"
WORKDIR /srv/combinellm
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /srv/combinellm/data \
    && chown appuser:appuser /srv/combinellm/data
COPY --from=builder /srv/combinellm/.venv ./.venv
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser scripts ./scripts
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
