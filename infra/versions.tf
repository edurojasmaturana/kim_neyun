terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Estado remoto centralizado en la cuenta gestora (750906968720).
  # `profile = kim2-admin` hace que el backend use SIEMPRE las credenciales de la
  # gestora, independiente del provider (que usa kim2-dev/kim2-prod por workspace).
  # Con workspaces, el state queda en env:/<workspace>/infra/terraform.tfstate.
  backend "s3" {
    bucket       = "kim-neyun-tfstate-750906968720"
    key          = "infra/terraform.tfstate"
    region       = "us-east-1"
    profile      = "kim2-admin"
    encrypt      = true
    use_lockfile = true # lock nativo de S3 (Terraform >= 1.10)
  }
}
