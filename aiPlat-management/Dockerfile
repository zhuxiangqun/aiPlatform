FROM python:3.11-slim

WORKDIR /app

# Management is a thin management plane — external deps only, no aiplat core/infra imports.
COPY aiPlat-management ./aiPlat-management
RUN pip install --no-cache-dir -e ./aiPlat-management

ENV PYTHONPATH=/app
ENV AIPLAT_HOME=/app/.aiplat
WORKDIR /app/aiPlat-management
EXPOSE 8000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "management.server:create_app"]
