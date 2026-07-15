FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN grep -v -E "PyQt|PySide|llama_cpp_python|openai-whisper" requirements.txt > requirements-server.txt && pip install --no-cache-dir -r requirements-server.txt

COPY . .

ENV PYTHONPATH=/app
ENV AIPLAT_HOME=/app/.aiplat
EXPOSE 8001

CMD ["uvicorn", "infra.management.api.main:create_app", "--host", "0.0.0.0", "--port", "8001", "--factory"]
