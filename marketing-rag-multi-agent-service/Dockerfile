FROM python:3.12-slim
WORKDIR /app
COPY marketing_rag ./marketing_rag
COPY run_server.py ./
EXPOSE 8000
CMD ["python", "run_server.py", "8000"]
