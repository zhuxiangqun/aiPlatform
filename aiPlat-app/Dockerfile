FROM python:3.11-slim

WORKDIR /app

# App depends on aiplat-platform (REST API). Root build context.
COPY aiPlat-infra ./aiPlat-infra
RUN pip install --no-cache-dir -e ./aiPlat-infra

COPY aiPlat-core ./aiPlat-core
RUN pip install --no-cache-dir -e ./aiPlat-core

COPY aiPlat-platform ./aiPlat-platform
RUN pip install --no-cache-dir -e ./aiPlat-platform

COPY aiPlat-app ./aiPlat-app
RUN pip install --no-cache-dir -e ./aiPlat-app && pip install --no-cache-dir gunicorn

ENV PYTHONPATH=/app
ENV AIPLAT_HOME=/app/.aiplat
WORKDIR /app/aiPlat-app
EXPOSE 8004

CMD ["gunicorn", "-c", "gunicorn.conf.py", "api.rest.routes:app"]
