# AccessiScan AI API + scanner worker image.
# The official Playwright image ships Python 3.12, Chromium 1.65.0 and every OS library Chromium needs,
# so browser scanning works without extra apt packages. Keep the tag in sync with `playwright==` in requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.65.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN python3 -m pip install --break-system-packages -r requirements.txt \
    && python3 -c "import playwright, sys; print('playwright', playwright.__version__ if hasattr(playwright, '__version__') else 'ok')"

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh && chown -R pwuser:pwuser /app

# Run as the image's unprivileged user. Chromium's own sandbox needs extra kernel privileges in most
# containers, so Playwright launches it with --no-sandbox; the container is the isolation boundary and
# all browser traffic goes through the in-process SSRF-guarded proxy (see SECURITY.md).
USER pwuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python3 -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health/live', timeout=4)"
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]
