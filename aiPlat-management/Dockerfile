FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN grep -v -E "PyQt|PySide|llama_cpp_python|openai-whisper" requirements.txt > requirements-server.txt && pip install --no-cache-dir -r requirements-server.txt

COPY . .

ENV PYTHONPATH=/app
ENV AIPLAT_HOME=/app/.aiplat
EXPOSE 8000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "management.server:create_app"]
