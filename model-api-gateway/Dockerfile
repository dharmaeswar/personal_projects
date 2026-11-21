# Model API Gateway — stdlib-only Python service, no third-party runtime deps.
# Multi-arch build: docker buildx build --platform linux/amd64,linux/arm64 -t model-api-gateway .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY gateway/ ./gateway/
COPY run_service.py ./

# Run as a non-root user; no package installs at runtime.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["python", "run_service.py"]
