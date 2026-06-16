terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Estado remoto: descomentar tras crear el bucket de estado.
  # backend "s3" {
  #   bucket       = "kim-neyun-tfstate-<sufijo>"
  #   key          = "infra/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true   # lock nativo de S3 (Terraform >= 1.10)
  # }
}
