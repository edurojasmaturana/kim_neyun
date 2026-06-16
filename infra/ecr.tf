# Repositorios de imágenes. force_delete=true para poder destruir en pruebas.

resource "aws_ecr_repository" "api" {
  name                 = "${local.name}/api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}

resource "aws_ecr_repository" "inference" {
  name                 = "${local.name}/inference"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${local.name}/frontend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}
