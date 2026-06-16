# API: Lambda (imagen de contenedor) + API Gateway HTTP API. Sin VPC: solo
# habla con DynamoDB por el endpoint público de AWS.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "api_basic" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "api_dynamo" {
  statement {
    sid       = "ReadPredicciones"
    actions   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:BatchGetItem"]
    resources = [aws_dynamodb_table.predicciones.arn]
  }
}

resource "aws_iam_role_policy" "api_dynamo" {
  name   = "${local.name}-api-dynamo"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_dynamo.json
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name}-api"
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
  architectures = ["arm64"]
  timeout       = 30
  memory_size   = 512

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.predicciones.name
      # Backend de usuarios vía Data API de Aurora (sin VPC en el Lambda).
      AURORA_CLUSTER_ARN = aws_rds_cluster.users.arn
      AURORA_SECRET_ARN  = aws_secretsmanager_secret.db.arn
      AURORA_DATABASE    = var.aurora_database
      JWT_SECRET         = random_password.jwt.result
    }
  }

  depends_on = [aws_cloudwatch_log_group.api]
  tags       = local.tags
}

resource "aws_apigatewayv2_api" "http" {
  name          = "${local.name}-http"
  protocol_type = "HTTP"
  tags          = local.tags
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
  tags        = local.tags
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGwInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
