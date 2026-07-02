FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV AIPLAT_HOME=/app/.aiplat
EXPOSE 8003

CMD ["uvicorn", "api.rest.routes:app", "--host", "0.0.0.0", "--port", "8003"]
