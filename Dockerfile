# ============================================================
# Inspector ITT - Dockerfile multi-arquitectura
# Funciona en: linux/amd64 (PC) y linux/arm64 (Arduino UNO Q)
# ============================================================

FROM python:3.11-slim-bookworm

# Metadatos
LABEL maintainer="ITT Tijuana"
LABEL description="Sistema de Inspección Modular con YOLO - Headless Web"

# Variables de entorno para Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Dependencias del sistema:
# - libglib2.0-0, libgomp1: requeridas por OpenCV/PyTorch
# - libgl1: requerido por OpenCV en algunas distros
# - curl: para healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Instalar dependencias Python forzando PyTorch CPU-only
# (extra-index-url permite tomar torch desde el repo CPU oficial)
COPY requirements-docker.txt ./requirements.txt
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Copiar código de la aplicación (cada COPY es una layer cacheable)
COPY database.py inspector.py app.py ./
COPY templates/ ./templates/
COPY static/ ./static/

# Crear directorios para volúmenes (vacíos)
RUN mkdir -p /app/modelos /data/capturas_defectos

# Variables de entorno por defecto (configurables al correr)
ENV INSPECTOR_DATA_DIR=/data \
    INSPECTOR_MODELOS_DIR=/app/modelos \
    INSPECTOR_CAMERA_IDX=0 \
    INSPECTOR_PORT=5000

# Puerto expuesto (HTTP del dashboard)
EXPOSE 5000

# Healthcheck: verifica que el endpoint de stats responda
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:5000/api/stats > /dev/null || exit 1

# Comando de arranque
CMD ["python", "-u", "app.py"]
