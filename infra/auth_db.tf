# Backend de usuarios: Aurora Serverless v2 (PostgreSQL) accedido por Data API.
#
# El cluster vive en una VPC mínima (Aurora siempre requiere subnets en >=2 AZ),
# pero el Lambda del API NO entra a la VPC: habla con la base por el Data API
# (HTTPS, endpoint de servicio AWS). Así se conserva el modelo serverless sin VPC,
# sin NAT y con escala a cero ($0 ocioso con min_capacity = 0).

# --- Red mínima (solo para alojar el cluster) -------------------------------

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "users" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = "${local.name}-users" })
}

# Dos subnets privadas (sin IGW/NAT): el cluster no necesita salida a internet.
resource "aws_subnet" "users" {
  count             = 2
  vpc_id            = aws_vpc.users.id
  cidr_block        = "10.20.${count.index + 1}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = merge(local.tags, { Name = "${local.name}-users-${count.index}" })
}

resource "aws_db_subnet_group" "users" {
  name       = "${local.name}-users"
  subnet_ids = aws_subnet.users[*].id
  tags       = local.tags
}

# SG del cluster: sin ingress (el Data API no entra por la SG). Egress abierto.
resource "aws_security_group" "users_db" {
  name        = "${local.name}-users-db"
  description = "Aurora users cluster (acceso solo via Data API)"
  vpc_id      = aws_vpc.users.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

# --- Credenciales (Secrets Manager) -----------------------------------------

resource "random_password" "db_master" {
  length  = 32
  special = false # evita caracteres problemáticos en el password del master
}

resource "aws_secretsmanager_secret" "db" {
  name = "${local.name}-users-db"
  tags = local.tags
}

# Formato esperado por el Data API: { username, password }.
resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = "kim_admin"
    password = random_password.db_master.result
  })
}

# Secreto de firma JWT (se inyecta como env var del Lambda API).
resource "random_password" "jwt" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "jwt" {
  name = "${local.name}-jwt"
  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id     = aws_secretsmanager_secret.jwt.id
  secret_string = random_password.jwt.result
}

# Secreto para firmar la cookie de sesión del backoffice /admin (SQLAdmin).
resource "random_password" "admin_session" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "admin_session" {
  name = "${local.name}-admin-session"
  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "admin_session" {
  secret_id     = aws_secretsmanager_secret.admin_session.id
  secret_string = random_password.admin_session.result
}

# --- Cluster Aurora Serverless v2 -------------------------------------------

resource "aws_rds_cluster" "users" {
  cluster_identifier = "${local.name}-users"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = var.aurora_engine_version
  database_name      = var.aurora_database
  master_username    = "kim_admin"
  master_password    = random_password.db_master.result

  db_subnet_group_name   = aws_db_subnet_group.users.name
  vpc_security_group_ids = [aws_security_group.users_db.id]

  # Data API (HTTP endpoint): permite consultar sin estar en la VPC.
  enable_http_endpoint = true

  serverlessv2_scaling_configuration {
    # min_capacity = 0 -> escala a cero tras inactividad (requiere provider AWS
    # reciente y engine >= 16.3). Sube a 0.5 si tu provider no lo soporta aún.
    min_capacity = var.aurora_min_capacity
    max_capacity = var.aurora_max_capacity
  }

  storage_encrypted   = true
  skip_final_snapshot = true # entorno no crítico; ajustar a false en producción dura

  tags = local.tags
}

resource "aws_rds_cluster_instance" "users" {
  identifier         = "${local.name}-users-1"
  cluster_identifier = aws_rds_cluster.users.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.users.engine
  engine_version     = aws_rds_cluster.users.engine_version

  tags = local.tags
}

# --- IAM: permite al Lambda API usar el Data API y leer los secretos ---------

data "aws_iam_policy_document" "api_users_db" {
  statement {
    sid = "AuroraDataApi"
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
    sid       = "ReadSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db.arn, aws_secretsmanager_secret.jwt.arn]
  }
}

resource "aws_iam_role_policy" "api_users_db" {
  name   = "${local.name}-api-users-db"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_users_db.json
}
