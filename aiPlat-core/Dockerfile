FROM python:3.11-slim

WORKDIR /app

# Core depends on aiplat-infra (model adapters). Build context is the repo root.
COPY aiPlat-infra ./aiPlat-infra
RUN pip install --no-cache-dir -e ./aiPlat-infra

COPY aiPlat-core ./aiPlat-core
RUN pip install --no-cache-dir -e ./aiPlat-core && pip install --no-cache-dir gunicorn

ENV PYTHONPATH=/app
ENV AIPLAT_HOME=/app/.aiplat
WORKDIR /app/aiPlat-core
EXPOSE 8002

CMD ["gunicorn", "-c", "gunicorn.conf.py", "server:app"]
