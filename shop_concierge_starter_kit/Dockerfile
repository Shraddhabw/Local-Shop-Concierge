FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root user; /data (SQLite) and /backups are created owned by it so named volumes inherit that.
RUN useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin app \
 && mkdir /data /backups && chown app:app /data /backups

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

# ONE worker on purpose: rate limiters and the AI cooldown live in memory.
# --no-proxy-headers: the app reads X-Forwarded-For itself, and only from the Caddy network.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--no-proxy-headers"]
