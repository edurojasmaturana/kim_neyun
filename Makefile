# Atajos de desarrollo y despliegue de KIM-NEYÜN.
.PHONY: help up down logs batch ddb-scan build-images tf-init tf-plan tf-apply lint \
        localstack-up localstack-down tf-local-plan tf-local-apply \
        migrate seed-admin auth-init

help:
	@echo "up           - levanta BD + API + dashboard (local)"
	@echo "batch        - corre el job de inferencia local (necesita ./models y ./data)"
	@echo "down         - apaga el entorno local"
	@echo "logs         - logs del entorno local"
	@echo "ddb-scan     - scan de la tabla DynamoDB local"
	@echo "lint         - compila (py_compile) todo el paquete app/"
	@echo "migrate      - aplica las migraciones de Alembic (tabla users) en Postgres local"
	@echo "seed-admin   - crea el usuario admin (ADMIN_EMAIL/ADMIN_PASSWORD, o defaults de dev)"
	@echo "auth-init    - migrate + seed-admin (deja la auth lista tras 'make up')"
	@echo "tf-init/plan/apply - Terraform en infra/"

up:
	docker compose up -d --build dynamodb api frontend
	@echo "API:       http://localhost:8000/docs"
	@echo "Dashboard: http://localhost:8501"

batch:
	docker compose --profile batch run --rm batch

down:
	docker compose down

logs:
	docker compose logs -f

ddb-scan:
	AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local \
	  aws dynamodb scan --table-name kim-neyun-predicciones \
	  --endpoint-url http://localhost:8001 --region us-east-1

# --- Auth: base de usuarios (Postgres local) ---------------------------------
# Tras `make up`, deja la auth lista para usar (tabla `users` + admin inicial).
# ADMIN_EMAIL/ADMIN_PASSWORD son opcionales; sin ellos usa valores de desarrollo
# (NO usar esos defaults fuera de un entorno local descartable).
migrate:
	docker compose exec api sh -c "cd /srv && alembic upgrade head"

seed-admin:
	docker compose exec \
	  -e ADMIN_EMAIL="$${ADMIN_EMAIL:-admin@kim-neyun.cl}" \
	  -e ADMIN_PASSWORD="$${ADMIN_PASSWORD:-KimNeyun2026Dev!}" \
	  -e ADMIN_FULL_NAME="$${ADMIN_FULL_NAME:-Administrador KIM-NEYÜN}" \
	  api sh -c "cd /srv && python -m scripts.seed_admin"

auth-init: migrate seed-admin

lint:
	python -m compileall -q app

tf-init:
	cd infra && terraform init

tf-plan:
	cd infra && terraform plan

tf-apply:
	cd infra && terraform apply

# --- Simular AWS en local con LocalStack (requiere: pip install terraform-local) ---
localstack-up:
	docker compose --profile localstack up -d localstack
	@echo "LocalStack en http://localhost:4566  (instala el wrapper: pip install terraform-local)"

localstack-down:
	docker compose --profile localstack down

# Plan COMPLETO contra LocalStack, 100% local y sin cuenta AWS.
tf-local-plan:
	cd infra && AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 \
	  sh -c 'tflocal init && tflocal plan'

# Apply contra LocalStack. Community cubre S3/ECR/Lambda/APIGW/Secrets/IAM/EventBridge;
# RDS/ECS-Fargate/App Runner necesitan LocalStack Pro.
tf-local-apply:
	cd infra && AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 \
	  sh -c 'tflocal init && tflocal apply'
