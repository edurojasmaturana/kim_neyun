# Job batch: Lambda (imagen de contenedor) disparada por EventBridge Scheduler.
# Sin VPC -> tiene salida a internet (Open-Meteo) y acceso a S3/DynamoDB.

resource "aws_iam_role" "batch" {
  name               = "${local.name}-batch"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "batch_basic" {
  role       = aws_iam_role.batch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "batch" {
  statement {
    sid = "ReadWritePredicciones"
    # GetItem: chequeo de idempotencia (run_batch salta proyecciones ya
    # calculadas para años cerrados, ver shared/repository.py).
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable", "dynamodb:CreateTable"]
    resources = [aws_dynamodb_table.predicciones.arn]
  }
  statement {
    sid       = "ReadArtifacts"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"]
  }
}

resource "aws_iam_role_policy" "batch" {
  name   = "${local.name}-batch"
  role   = aws_iam_role.batch.id
  policy = data.aws_iam_policy_document.batch.json
}

resource "aws_cloudwatch_log_group" "batch" {
  name              = "/aws/lambda/${local.name}-batch"
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_lambda_function" "batch" {
  function_name = "${local.name}-batch"
  role          = aws_iam_role.batch.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.inference.repository_url}:${var.image_tag}"
  # x86_64: torch==2.10.0 / xgboost==3.2.0 (versiones con las que se entrenaron
  # los .pkl, incluidos XGBoost_Hybrid_*.pkl pickleados con xgboost 3.2.0) no
  # publican wheels aarch64; la API (sin estas deps) sigue en arm64.
  architectures = ["x86_64"]
  timeout       = var.batch_timeout
  memory_size   = var.batch_memory

  ephemeral_storage {
    size = var.batch_ephemeral_mb
  }

  environment {
    variables = {
      DYNAMODB_TABLE    = aws_dynamodb_table.predicciones.name
      MODELS_DIR        = "/tmp/models"
      MODELS_S3_URI     = "s3://${aws_s3_bucket.artifacts.bucket}/models/"
      HISTORIA_S3_URI   = "s3://${aws_s3_bucket.artifacts.bucket}/data/API_Epidemiologia_Temuco_Padre_Las_Casas.csv"
      ANIOS_PROYECCION  = var.anios_proyeccion
      ALERTA_THRESHOLD  = tostring(var.alerta_threshold)
      KIM_BACKFILL_FULL = var.batch_backfill_full ? "1" : "0"
      HF_HOME           = "/tmp/hf"
    }
  }

  depends_on = [aws_cloudwatch_log_group.batch]
  tags       = local.tags
}

# --- EventBridge Scheduler -> Lambda ---

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeBatch"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.batch.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${local.name}-scheduler"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "batch" {
  name = "${local.name}-batch"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.batch_schedule
  schedule_expression_timezone = var.batch_timezone

  target {
    arn      = aws_lambda_function.batch.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
