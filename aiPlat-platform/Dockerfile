FROM python:3.11-slim

WORKDIR /app

# Platform depends on aiplat-core (+ its aiplat-infra dependency). Root context.
COPY aiPlat-infra ./aiPlat-infra
RUN pip install --no-cache-dir -e ./aiPlat-infra

COPY aiPlat-core ./aiPlat-core
RUN pip install --no-cache-dir -e ./aiPlat-core

COPY aiPlat-platform ./aiPlat-platform
RUN pip install --no-cache-dir -e ./aiPlat-platform

ENV PYTHONPATH=/app
ENV AIPLAT_HOME=/app/.aiplat
WORKDIR /app/aiPlat-platform
EXPOSE 8003

CMD ["gunicorn", "-c", "gunicorn.conf.py", "api.rest.routes:app"]
