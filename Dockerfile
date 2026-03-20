FROM python:3.12-slim

# Evita que Python genere archivos .pyc y asegura que los logs salgan directo a la consola
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/code 

WORKDIR /code

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el proyecto al directorio /code
COPY . .

# Permisos de usuario
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /code
USER appuser

# Exponemos el puerto
EXPOSE 8000

# Comando de inicio: 
# 1. Corremos migraciones.
# 2. Arrancamos uvicorn apuntando a la carpeta app.main
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]