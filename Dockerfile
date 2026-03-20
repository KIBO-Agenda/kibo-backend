FROM python:3.12-slim

# Evitamos archivos .pyc y forzamos logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/code

WORKDIR /code

# Dependencias del sistema para PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalación de librerías
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el proyecto
COPY . .

# Permisos de usuario para seguridad
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /code
USER appuser

# Exponemos el puerto que usa Railway
EXPOSE 8000

# COMANDO DE INICIO:
# 1. Ejecuta migraciones
# 2. Inicia uvicorn usando el módulo app.main
CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]