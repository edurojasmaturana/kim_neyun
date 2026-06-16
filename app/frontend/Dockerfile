# Imagen del dashboard Streamlit (sirve para local y para el EC2 de AWS).
# Build context = carpeta app/  ->  docker build -f frontend/Dockerfile .
#
# En AWS corre en un EC2 t4g.micro (arm64, Docker + Caddy como proxy TLS;
# App Runner no soporta WebSocket y Streamlit lo requiere, ver
# CHECKPOINT.md). Para AWS, construir con:
#   docker build --platform linux/arm64 -f frontend/Dockerfile -t <tag> .
# (ver infra/README.md, paso "Build & push"). El build local via
# docker-compose usa la arquitectura nativa del host, sin pin de plataforma.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/srv
WORKDIR /srv

COPY frontend/requirements.txt ./
RUN pip install -r requirements.txt

COPY shared/ ./shared/
COPY frontend/ ./frontend/

# Caddy hace reverse proxy a este puerto (red docker "kimnet").
EXPOSE 8501
CMD ["streamlit", "run", "frontend/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
