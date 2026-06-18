# Cada workspace opera en su propia cuenta AWS con su propio perfil CLI.
# Org nueva o-mq50svs8i7 (gestora 750906968720). El state vive en account
# 735252692369 (dev) / 794457362573 (prod); usar el perfil equivocado intentaría
# recrear toda la infra en otra cuenta.
# Por eso NO se permite el workspace "default": el lookup falla a propósito si
# alguien olvida hacer `terraform workspace select dev|prod`.
locals {
  workspace_profile = {
    dev  = "kim2-dev"
    prod = "kim2-prod"
  }[terraform.workspace]

  workspace_account = {
    dev  = "735252692369"
    prod = "794457362573"
  }[terraform.workspace]
}

provider "aws" {
  region  = var.region
  profile = local.workspace_profile

  # Salvaguarda: aborta si las credenciales no son de la cuenta esperada
  # para este workspace (p.ej. perfil mal configurado).
  allowed_account_ids = [local.workspace_account]
}

data "aws_caller_identity" "current" {}

locals {
  name = var.project

  tags = {
    Project   = var.project
    ManagedBy = "terraform"
  }
}
