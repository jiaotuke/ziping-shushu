FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    ZIPING_PUBLIC_SITE=1 \
    ZIPING_PORTABLE=1 \
    ZIPING_ALLOW_REFERRAL_DEMO=0 \
    ZIPING_RESOURCE_ROOT=/app \
    ZIPING_USER_DATA=/var/lib/ziping/runtime \
    ZIPING_PUBLIC_DATA=/var/lib/ziping/public

WORKDIR /app
COPY site/requirements-public.txt ./requirements-public.txt
RUN python -m pip install --no-cache-dir -r requirements-public.txt \
    && groupadd --gid 10001 ziping \
    && useradd --uid 10001 --gid ziping --no-create-home ziping \
    && mkdir -p /var/lib/ziping/public /var/lib/ziping/runtime /var/lib/ziping/backups \
    && chown -R ziping:ziping /var/lib/ziping
COPY site/ ./
COPY maintenance/ ./maintenance/
USER ziping

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).read()"
ENTRYPOINT ["python", "-m", "streamlit", "run", "public_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--server.fileWatcherType=none", "--browser.gatherUsageStats=false"]
