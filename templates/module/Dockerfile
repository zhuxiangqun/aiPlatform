# Product runtime image stub (P0 skeleton — not production-hardened).
# Replace BASE and CMD per product.
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
EXPOSE 8080
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')" || exit 1
CMD ["python", "-c", "print('templates/product stub — replace with product entrypoint')"]
