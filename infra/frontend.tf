# Frontend: Streamlit en EC2 (Docker, arm64) detrás de Caddy con TLS
# autofirmado (`tls internal`). App Runner NO soporta WebSocket (Envoy
# devuelve 403 a `Upgrade: websocket`) y Streamlit lo requiere para
# `_stcore/stream` -- ver CHECKPOINT.md, sección "Desplegado en AWS (kim-dev)".

data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
  filter {
    name   = "availabilityZone"
    values = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d", "us-east-1f"]
  }
}

resource "aws_security_group" "frontend" {
  name        = "${local.name}-frontend"
  description = "Dashboard Streamlit (HTTPS publico, via Caddy)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP (Lets Encrypt HTTP-01 challenge)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "frontend" {
  name               = "${local.name}-frontend"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = local.tags
}

# Pull de la imagen del dashboard desde ECR.
resource "aws_iam_role_policy_attachment" "frontend_ecr" {
  role       = aws_iam_role.frontend.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Acceso remoto (Session Manager) sin abrir el puerto 22 ni manejar key pairs.
resource "aws_iam_role_policy_attachment" "frontend_ssm" {
  role       = aws_iam_role.frontend.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "frontend" {
  name = "${local.name}-frontend"
  role = aws_iam_role.frontend.name
}

# Se crea antes que la instancia: el Caddyfile necesita conocer esta IP para
# emitir el certificado autofirmado con la IP como SAN (ver frontend_user_data.sh.tpl).
resource "aws_eip" "frontend" {
  domain = "vpc"
  tags   = local.tags
}

resource "aws_instance" "frontend" {
  ami                         = data.aws_ssm_parameter.al2023_arm64.value
  instance_type               = "t4g.micro"
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.frontend.id]
  iam_instance_profile        = aws_iam_instance_profile.frontend.name
  associate_public_ip_address = true

  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/frontend_user_data.sh.tpl", {
    ecr_image    = "${aws_ecr_repository.frontend.repository_url}:${var.image_tag}"
    api_base_url = aws_apigatewayv2_api.http.api_endpoint
    region       = var.region
    frontend_ip  = aws_eip.frontend.public_ip
    domain_name  = var.domain_name
  })

  tags = local.tags

  # `al2023_arm64` apunta al AMI "latest" (parámetro SSM): AWS publica builds
  # nuevos periódicamente, lo que generaba un `must be replaced` en cada
  # `plan` sin que nadie haya tocado esta config. Se ignora para no reemplazar
  # la instancia (y su IP/estado) por cada parche de AMI; para actualizar el
  # AMI a propósito, hacer `terraform taint aws_instance.frontend` o quitar
  # este lifecycle temporalmente.
  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_eip_association" "frontend" {
  instance_id   = aws_instance.frontend.id
  allocation_id = aws_eip.frontend.id
}
