# syntax=docker/dockerfile:1
# Multi-stage build for the demo web service (stdlib only, no deps).
FROM python:3.12-slim AS builder
WORKDIR /app
COPY service/ ./service/
COPY run_service.py ./
# No third-party dependencies to install; stage kept to show the pattern.

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app /app
# Run as a non-root user.
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser
ENV PORT=8080
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"
CMD ["python", "run_service.py"]
