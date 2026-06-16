# Persistencia: DynamoDB (predicciones) + bucket S3 (artefactos del modelo).

resource "aws_dynamodb_table" "predicciones" {
  name         = "${local.name}-predicciones"
  billing_mode = "PAY_PER_REQUEST" # escala a cero, ideal para volumen bajo
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  tags = local.tags
}

# Bucket de artefactos: modelos .pkl (prefijo models/) y CSV DEIS (data/).
resource "aws_s3_bucket" "artifacts" {
  bucket = "${local.name}-artifacts-${data.aws_caller_identity.current.account_id}"
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
