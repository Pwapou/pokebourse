FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

WORKDIR /opt/pokemon-arbitrage

COPY pyproject.toml README.md ./
COPY app ./app
COPY scripts ./scripts

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --create-home app \
    && pip install --no-cache-dir . \
    && playwright install --with-deps chromium \
    && mkdir -p /data /opt/pw-browsers \
    && chown -R app:app /data /opt/pw-browsers

USER app
VOLUME ["/data"]

FROM base AS development
USER root
COPY tests ./tests
RUN pip install --no-cache-dir ".[dev]"
USER app
CMD ["pytest"]

FROM base AS production
CMD ["uvicorn", "app.web:app", "--host", "0.0.0.0", "--port", "8000"]
