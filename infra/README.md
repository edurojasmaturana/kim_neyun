# Infraestructura (Terraform) — KIM-NEYÜN

Región: **us-east-1**. **Full serverless** salvo el frontend (ver abajo); sin
ECS/RDS/NAT. Ver `../CHECKPOINT.md`.

## Recursos que crea
- **DynamoDB**: tabla `kim-neyun-predicciones` (PAY_PER_REQUEST, clave pk/sk).
- **S3**: bucket de artefactos (modelos `.pkl` en `models/`, CSV DEIS en `data/`).
- **ECR**: 3 repos (`api`, `inference`, `frontend`).
- **API**: Lambda (imagen arm64, sin VPC) + API Gateway HTTP API.
- **Batch**: Lambda (imagen **x86_64**, sin VPC) + EventBridge Scheduler (semanal).
  `torch==2.10.0`/`xgboost==3.2.0` (versiones con las que se entrenaron los
  `.pkl`) no publican wheels aarch64; por eso esta Lambda va en x86_64 (la API,
  sin esas deps, sigue en arm64).
- **Frontend**: EC2 `t4g.micro` (arm64, Amazon Linux 2023) corriendo Docker:
  contenedor Streamlit + proxy **Caddy** (TLS autofirmado vía `tls internal`,
  Elastic IP). **No usa App Runner**: App Runner no soporta WebSocket (Envoy
  responde 403 a `Upgrade: websocket`) y Streamlit lo requiere para
  `_stcore/stream`. El navegador mostrará advertencia de certificado no
  confiable (autofirmado) — aceptar para continuar. Ver CHECKPOINT.md.
- **Auth**: Aurora Serverless v2 PostgreSQL (`min_capacity = 0`, escala a cero)
  en VPC mínima propia, accedido por **Data API** (el Lambda API no entra a la
  VPC) + 2 secretos en Secrets Manager (db, jwt).
- **Apagado/encendido del frontend**: 2 EventBridge Schedules que prenden la EC2
  a las 08:00 y la apagan a las 20:00 (L-V, hora Chile) vía API EC2 directa
  (universal target, sin Lambda). Configurable: `frontend_on_hour`,
  `frontend_off_hour`, `frontend_schedule_days` (`"*"` para todos los días).
- IAM mínimo + Log Groups.

## Costos

Estimación mensual en `us-east-1`, **1000 requests/día** (≈30k/mes). El nº de
requests es casi irrelevante: el costo lo fija lo que está encendido 24/7, no el
tráfico (todo lo pago-por-uso suma centavos).

| Componente | Supuesto | US$/mes |
|---|---|---|
| **EC2 frontend** `t4g.micro` | con apagado L-V 20:00–08:00 (~260 h/mes) | ~2.2 |
| **EIP / IPv4 pública** | cobro AWS por IPv4 (también si está apagado) | ~3.65 |
| EBS root (gp3) | disco del AMI AL2023 | ~1 |
| **Aurora Serverless v2** (auth) | `min=0` → ~US$0 ocioso; sube si el login la mantiene despierta | ~0–15 |
| Secrets Manager | 2 secretos × US$0.40 | ~0.8 |
| ECR | 3 repos (inference grande + api + frontend) | ~0.8 |
| CloudWatch Logs | retención 14 días, bajo volumen | ~0.5–1.5 |
| Lambda batch | x86_64 3008 MB, ~10 min, **semanal** | ~0.15 |
| Lambda API | arm64 512 MB, dentro de free tier | ~0 |
| DynamoDB | PAY_PER_REQUEST | ~0.05 |
| API Gateway HTTP | 30k req × US$1/M | ~0.03 |
| S3 artefactos | `.pkl` + CSV | ~0.10 |
| **Total** | | **~US$13–15/mes** |

Drivers fijos: EC2 + EBS + EIP. **Comodín: Aurora** — con logins esporádicos
escala a cero (~US$0); si el tráfico de auth la mantiene despierta puede sumar
US$10–15. **Sin el apagado programado** el EC2 sube de ~US$2.2 a ~US$6 (total
~US$17–29). La EIP sigue cobrando ~US$3.65 aunque la instancia esté apagada.

> Presupuesto del MVP ~US$1.800 → con ~US$15/mes alcanza para ~8 años de operación.

## Orden de despliegue (las imágenes deben existir antes que las Lambdas)

```bash
cd infra
terraform init

# 1) Crear primero ECR + bucket
terraform apply \
  -target=aws_ecr_repository.api \
  -target=aws_ecr_repository.inference \
  -target=aws_ecr_repository.frontend \
  -target=aws_s3_bucket.artifacts

# 2) Login a ECR
ACC=$(aws sts get-caller-identity --query Account --output text)
REG=us-east-1
aws ecr get-login-password --region $REG | docker login --username AWS --password-stdin $ACC.dkr.ecr.$REG.amazonaws.com

# 3) Build & push (contexto = ../app). API y frontend en arm64; inference en amd64
#    (torch==2.10.0/xgboost==3.2.0 no publican wheels aarch64 -> batch va x86_64).
API=$(terraform output -raw ecr_api)
INF=$(terraform output -raw ecr_inference)
FE=$(terraform output -raw ecr_frontend)

docker build --platform linux/arm64 -f ../app/api/Dockerfile       -t $API:latest ../app && docker push $API:latest
docker build --platform linux/amd64 -f ../app/inference/Dockerfile -t $INF:latest ../app && docker push $INF:latest
docker build --platform linux/arm64 -f ../app/frontend/Dockerfile  -t $FE:latest  ../app && docker push $FE:latest

# 4) Subir artefactos del modelo y el histórico al bucket
BUCKET=$(terraform output -raw artifacts_bucket)
aws s3 sync ../models   s3://$BUCKET/models/
aws s3 cp   ../data/API_Epidemiologia_Temuco_Padre_Las_Casas.csv s3://$BUCKET/data/

# 5) Crear el resto
terraform apply
```

## URLs públicas (gratis, sin dominio propio)

AWS entrega un endpoint de API permanente; el frontend usa la Elastic IP del
EC2. No se necesita comprar dominio. Tras `terraform apply`:

```bash
cd infra
terraform output api_url        # https://{api-id}.execute-api.us-east-1.amazonaws.com
terraform output frontend_url   # https://<elastic-ip> (dashboard, cert autofirmado)
```

### Documentación de la API (Swagger, autogenerada por FastAPI)
La API expone su doc interactiva en estas rutas (consumibles por el equipo front):

| Recurso | Ruta |
|---|---|
| Swagger UI | `<api_url>/docs` |
| ReDoc | `<api_url>/redoc` |
| Spec OpenAPI (para generar cliente) | `<api_url>/openapi.json` |

> **Está pública de momento** (sin auth). Si más adelante se quiere cerrar, ver
> nota abajo.
>
> **No requiere `root_path`**: el API Gateway usa el stage `$default` (sin prefijo
> de ruta), así que `/docs` funciona directo en la URL de `execute-api`. La var de
> entorno `API_ROOT_PATH` queda vacía. Solo habría que setearla (p.ej. `/prod`) si
> se migrara a un stage con nombre.
>
> Cuando se consiga un dominio propio, se mapea encima (custom domain en API
> Gateway / DNS hacia la Elastic IP del frontend) **sin cambiar código**: las
> URLs feas de `execute-api` y la IP pública seguirán funcionando como fallback.
> Con un dominio real, Caddy puede pasar de `tls internal` (autofirmado) a
> Let's Encrypt automático (sin advertencia del navegador).

## Correr el job batch manualmente (sin esperar el cron)
```bash
aws lambda invoke --function-name $(terraform output -raw batch_function_name) \
  --cli-read-timeout 0 /dev/stdout
```
Revisa logs en CloudWatch (`/aws/lambda/kim-neyun-batch`) y abre `frontend_url`.
Inspecciona datos: `aws dynamodb scan --table-name $(terraform output -raw dynamodb_table)`.

## Simular en local (sin cuenta AWS)

Dos cosas distintas se pueden "simular":
- **El sistema corriendo** (DynamoDB Local + API + dashboard + job): `make up` /
  `make batch` (docker-compose). Reproduce el comportamiento real.
- **El aprovisionamiento de Terraform**: con **LocalStack** (emulador de AWS).

```bash
make localstack-up           # levanta LocalStack en :4566
pip install terraform-local  # provee el comando `tflocal`
make tf-local-plan           # plan COMPLETO, 100% local y sin cuenta AWS
```
- `tflocal plan` funciona para toda la config (no requiere que los servicios
  existan) → forma fiel de ver "qué haría Terraform", local y gratis.
- `make tf-local-apply` los crea en el emulador. **Community** cubre casi todo
  (DynamoDB, S3, ECR, Lambda, API Gateway, EventBridge, IAM, EC2); **Aurora
  Serverless v2** y algunas APIs avanzadas requieren LocalStack Pro.

> Que LocalStack acepte un `apply` no garantiza que AWS real lo acepte (los mocks
> difieren). Para el "qué haría" más fiel sin crear nada, `terraform plan` contra
> AWS real (solo lectura, gratis) sigue siendo lo ideal.

## Notas
- Estado remoto: descomenta el bloque `backend "s3"` en `versions.tf` tras crear
  el bucket de estado.
- La Lambda batch tiene **timeout 15 min** (máx). Si el job creciera, baja
  `ANIOS_PROYECCION` al año en curso para el cron y haz el backfill aparte.
- `terraform destroy` elimina todo (ECR con force_delete; DynamoDB on-demand).
