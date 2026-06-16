# KIM-NEYÜN: Motor de Predicción Respiratoria
# Imagen pineada por digest para builds reproducibles en AWS (CodeBuild/ECR).
# 'python:3.12-slim' a secas flota al último patch y rompe la reproducibilidad.
# Para actualizar: docker pull python:3.12-slim && docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94

# Instalamos dependencias del sistema necesarias (git para Chronos)
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiamos los archivos de requerimientos e instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el proyecto al contenedor
COPY . .

# Exponemos los puertos (8000 para FastAPI, 7860 para Streamlit)
EXPOSE 8000
EXPOSE 7860

# Script de inicio para correr ambos procesos
RUN echo '#!/bin/bash\n\
uvicorn api_motor:app --host 0.0.0.0 --port 8000 &\n\
streamlit run app.py --server.port 7860 --server.address 0.0.0.0\n\
' > start.sh && chmod +x start.sh

# Ejecutamos el script
CMD ["./start.sh"]