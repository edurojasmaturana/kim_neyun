# Imagen del job batch para AWS Lambda (contenedor, x86_64).
# Build context = carpeta app/  ->  docker build --platform linux/amd64 -f inference/Dockerfile .
#
# Base NO oficial de Lambda (python:3.11-slim) + Lambda Runtime Interface Client
# (awslambdaric). Motivo: torch==2.10.0 / xgboost==3.2.0 (versiones con las que
# se entrenaron los .pkl, incluidos XGBoost_Hybrid_*.pkl pickleados con xgboost
# 3.2.0) no tienen wheels compatibles con la base oficial
# public.ecr.aws/lambda/python:3.11 (manylinux/glibc viejos) en NINGUNA
# arquitectura. python:3.11-slim sí las tiene (misma base que
# inference/Dockerfile.local, ya validada localmente). Patrón soportado por AWS
# para "Lambda con imagen base propia":
# https://docs.aws.amazon.com/lambda/latest/dg/images-create.html#images-create-from-base
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /var/task

COPY inference/requirements.txt ./

# torch CPU-only: el índice por defecto de PyPI en linux/amd64 trae el build con
# CUDA (arrastra ~5-6 GB de paquetes nvidia-*-cu12 inútiles en Lambda, sin GPU).
# Se instala primero desde el índice CPU de PyTorch; el -r requirements.txt
# posterior ve torch==2.10.0 ya satisfecho y no lo reemplaza.
RUN pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt awslambdaric

# Pesos de Chronos horneados en la imagen, para no depender de Hugging Face en
# cada arranque. OJO: deben ir a una ruta PERSISTENTE de la imagen (/opt/hf),
# NO a /tmp, porque Lambda monta un /tmp vacío y efímero en runtime y el caché
# se perdería. HF_HOME se fija antes del bake para que el caché quede en /opt/hf.
ENV HF_HOME=/opt/hf
RUN python -c "import torch; from chronos import ChronosPipeline; \
    ChronosPipeline.from_pretrained('amazon/chronos-t5-small', device_map='cpu', torch_dtype=torch.bfloat16)"

COPY shared/ ./shared/
COPY inference/ ./inference/

# Los .pkl se sincronizan de S3 en runtime: van a /tmp (único FS escribible).
# HF_HOME se mantiene en /opt/hf (heredado arriba) para usar el modelo horneado.
ENV MODELS_DIR=/tmp/models

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["inference.handler.handler"]
