# CI/CD del frontend: GitHub Actions construye/publica la imagen a ECR y
# redeploya en el EC2 vía SSM, autenticándose con OIDC (sin claves de larga
# duración). El rol solo es asumible desde el repo y la rama exactos (sub
# claim de GitHub), nunca desde un fork o una rama distinta.
#
# Verificado antes de escribir este archivo (2026-06-23, cuenta 735252692369,
# perfil kim2-dev): `aws iam list-open-id-connect-providers` no devuelve nada
# -> no hay un provider OIDC de GitHub ya gestionado (a mano o por otro
# Terraform) en esta cuenta. Si en el futuro `terraform plan` fallara por
# "EntityAlreadyExists" en este recurso, hay que reemplazar el `resource` de
# abajo por un `data "aws_iam_openid_connect_provider"` apuntando al ARN
# existente (o hacer `terraform import`), no recrearlo.

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  # thumbprint_list es opcional desde el provider AWS ~5.x para IdPs que AWS
  # reconoce (GitHub es uno): valida contra la cadena de confianza de la IdP
  # en vez de un hash fijo que se rompe cada vez que GitHub rota su CA. AWS
  # igual autocompleta este campo al crear el recurso; se ignora para que no
  # quede como diff perpetuo en cada `plan`.
  thumbprint_list = []

  lifecycle {
    ignore_changes = [thumbprint_list]
  }

  tags = local.tags
}

# --- Rol que asume GitHub Actions (sts:AssumeRoleWithWebIdentity) -----------

data "aws_iam_policy_document" "github_actions_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Restringido al repo y rama exactos: ni forks, ni otras ramas, ni PRs
    # pueden asumir este rol (el claim `sub` de GitHub codifica repo+ref).
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:edurojasmaturana/kim_neyun:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions_deploy_frontend" {
  name               = "github-actions-deploy-frontend"
  assume_role_policy = data.aws_iam_policy_document.github_actions_trust.json
  tags               = local.tags
}

# --- Permisos mínimos: push a ECR (solo repo frontend) + redeploy por SSM --

data "aws_iam_policy_document" "github_actions_deploy_frontend" {
  statement {
    sid       = "ECRAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "ECRPushFrontend"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.frontend.arn]
  }

  statement {
    sid       = "DescribeInstances"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }

  # Encender la instancia si el schedule la apagó antes de un deploy fuera de
  # horario (ver infra/frontend_schedule.tf). Acotado por tag, no por ID fijo,
  # porque el ID cambia si Terraform reemplaza la instancia
  # (`user_data_replace_on_change = true` en frontend.tf).
  statement {
    sid       = "StartFrontendByTag"
    actions   = ["ec2:StartInstances"]
    resources = ["arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [var.project]
    }
  }

  statement {
    sid       = "SSMDocument"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ssm:${var.region}::document/AWS-RunShellScript"]
  }

  statement {
    sid       = "SSMSendToFrontendByTag"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [var.project]
    }
  }

  statement {
    sid = "SSMReadResults"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
      "ssm:DescribeInstanceInformation",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions_deploy_frontend" {
  name   = "github-actions-deploy-frontend"
  role   = aws_iam_role.github_actions_deploy_frontend.id
  policy = data.aws_iam_policy_document.github_actions_deploy_frontend.json
}

output "github_actions_role_arn" {
  description = "ARN a pegar como secret AWS_DEPLOY_ROLE_ARN en GitHub (Settings > Secrets and variables > Actions)."
  value       = aws_iam_role.github_actions_deploy_frontend.arn
}

# --- Rol para deploy de la API (distinto del frontend, mínimo privilegio) ----

data "aws_iam_policy_document" "github_actions_deploy_api" {
  statement {
    sid       = "ECRAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "ECRPushApi"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.api.arn]
  }

  statement {
    sid = "LambdaUpdateCode"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
    ]
    resources = [
      "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${local.name}-api"
    ]
  }

  statement {
    sid = "AlembicDataApi"
    actions = [
      "rds-data:ExecuteStatement",
      "rds-data:BatchExecuteStatement",
      "rds-data:BeginTransaction",
      "rds-data:CommitTransaction",
      "rds-data:RollbackTransaction",
    ]
    resources = [aws_rds_cluster.users.arn]
  }

  statement {
    sid       = "AlembicSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db.arn]
  }
}

resource "aws_iam_role" "github_actions_deploy_api" {
  name               = "github-actions-deploy-api"
  assume_role_policy = data.aws_iam_policy_document.github_actions_trust.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "github_actions_deploy_api" {
  name   = "github-actions-deploy-api"
  role   = aws_iam_role.github_actions_deploy_api.id
  policy = data.aws_iam_policy_document.github_actions_deploy_api.json
}

output "github_actions_api_role_arn" {
  description = "ARN a pegar como secret AWS_DEPLOY_API_ROLE_ARN en GitHub."
  value       = aws_iam_role.github_actions_deploy_api.arn
}
