FROM python:3.12-slim
WORKDIR /app
COPY inventory_orchestration/ ./inventory_orchestration/
COPY run_service.py ./
EXPOSE 8000
CMD ["python3", "run_service.py"]
