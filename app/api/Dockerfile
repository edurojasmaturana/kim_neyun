# Imagen de la API para AWS Lambda (contenedor).
# Build context = carpeta app/  ->  docker build --platform linux/arm64 -f api/Dockerfile .
FROM public.ecr.aws/lambda/python:3.11

COPY api/requirements.txt ./
RUN pip install -r requirements.txt

COPY shared/ ${LAMBDA_TASK_ROOT}/shared/
COPY api/ ${LAMBDA_TASK_ROOT}/api/

# handler = Mangum(app) en api/main.py
CMD ["api.main.handler"]
