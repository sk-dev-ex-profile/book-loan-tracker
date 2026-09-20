FROM python:3.14.6-slim@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POLKA_DB=/app/data/polka.db \
    POLKA_HOST=0.0.0.0 \
    POLKA_PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS checks
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
RUN python scripts/check.py

FROM base AS runtime
RUN useradd --uid 10001 --create-home polka \
    && mkdir -p /app/data \
    && chown polka:polka /app/data
COPY library.py polka.py web.py ./
COPY migrations ./migrations
COPY templates ./templates
COPY static ./static
USER polka
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["python", "web.py"]
