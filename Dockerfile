FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRACETRUST_DATA_ROOT=/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY tracetrust ./tracetrust

RUN pip install . \
    && useradd --create-home --uid 10001 tracetrust \
    && mkdir -p /data \
    && chown -R tracetrust:tracetrust /app /data

USER tracetrust

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"

CMD ["uvicorn", "tracetrust.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
