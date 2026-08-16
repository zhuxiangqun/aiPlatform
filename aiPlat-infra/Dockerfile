FROM python:3.11-slim

WORKDIR /app

# Infra is Layer 0 — no internal dependencies. Root build context.
COPY aiPlat-infra ./aiPlat-infra
RUN pip install --no-cache-dir -e ./aiPlat-infra && pip install --no-cache-dir gunicorn

ENV PYTHONPATH=/app
ENV AIPLAT_HOME=/app/.aiplat
WORKDIR /app/aiPlat-infra
EXPOSE 8001

CMD ["gunicorn", "-c", "gunicorn.conf.py", "infra.management.api.main:create_app"]
