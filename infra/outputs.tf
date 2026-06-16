output "api_url" {
  description = "URL base del API Gateway (consumida por el dashboard)."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "frontend_url" {
  description = "URL pública del dashboard (EC2 + Caddy, cert TLS autofirmado)."
  value       = "https://${aws_eip.frontend.public_ip}"
}

output "ecr_api" {
  value = aws_ecr_repository.api.repository_url
}

output "ecr_inference" {
  value = aws_ecr_repository.inference.repository_url
}

output "ecr_frontend" {
  value = aws_ecr_repository.frontend.repository_url
}

output "artifacts_bucket" {
  description = "Bucket S3 para subir models/ y data/."
  value       = aws_s3_bucket.artifacts.bucket
}

output "dynamodb_table" {
  value = aws_dynamodb_table.predicciones.name
}

output "batch_function_name" {
  description = "Lambda del job batch (para invocarla a mano)."
  value       = aws_lambda_function.batch.function_name
}

# --- Backend de usuarios (para correr migraciones/seed vía Data API) ---

output "aurora_cluster_arn" {
  description = "ARN del cluster Aurora (export AURORA_CLUSTER_ARN para alembic/seed)."
  value       = aws_rds_cluster.users.arn
}

output "aurora_secret_arn" {
  description = "ARN del secreto de credenciales (export AURORA_SECRET_ARN)."
  value       = aws_secretsmanager_secret.db.arn
}

output "aurora_database" {
  description = "Nombre de la base de usuarios."
  value       = var.aurora_database
}
