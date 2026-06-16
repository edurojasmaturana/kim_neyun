# Apagado/encendido programado del EC2 del dashboard para ahorrar costo.
#
# El frontend (t4g.micro) corre 24/7 por defecto (~US$6/mes + EBS + EIP). Como
# el uso es de demo/horario laboral, lo apagamos fuera de horario: dos
# EventBridge Schedules llaman directo a la API EC2 (universal target
# "aws-sdk:ec2") sin Lambda intermedio.
#
# - Enciende  08:00 hora Chile (var.frontend_on_cron)
# - Apaga     20:00 hora Chile (var.frontend_off_cron)
# - Días: lun-vie por defecto (var.frontend_schedule_days). Pon "*" si necesitas
#   demos en fin de semana.
#
# OJO: la EIP (aws_eip.frontend) sigue cobrando ~US$3.65/mes aunque la instancia
# esté detenida; el ahorro viene del cómputo del EC2, no del IPv4.

locals {
  # cron(min hora día-mes mes día-semana año) en hora de var.frontend_timezone.
  frontend_on_cron  = "cron(0 ${var.frontend_on_hour} ? * ${var.frontend_schedule_days} *)"
  frontend_off_cron = "cron(0 ${var.frontend_off_hour} ? * ${var.frontend_schedule_days} *)"
}

# Rol que asume EventBridge Scheduler para arrancar/detener la instancia.
resource "aws_iam_role" "frontend_scheduler" {
  name               = "${local.name}-frontend-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "frontend_scheduler" {
  statement {
    sid       = "StartStopFrontend"
    actions   = ["ec2:StartInstances", "ec2:StopInstances"]
    resources = [aws_instance.frontend.arn]
  }
}

resource "aws_iam_role_policy" "frontend_scheduler" {
  name   = "${local.name}-frontend-scheduler"
  role   = aws_iam_role.frontend_scheduler.id
  policy = data.aws_iam_policy_document.frontend_scheduler.json
}

# --- Encendido (08:00 hora Chile) ---
resource "aws_scheduler_schedule" "frontend_start" {
  name = "${local.name}-frontend-start"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = local.frontend_on_cron
  schedule_expression_timezone = var.frontend_timezone

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = aws_iam_role.frontend_scheduler.arn

    input = jsonencode({
      InstanceIds = [aws_instance.frontend.id]
    })
  }
}

# --- Apagado (20:00 hora Chile) ---
resource "aws_scheduler_schedule" "frontend_stop" {
  name = "${local.name}-frontend-stop"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = local.frontend_off_cron
  schedule_expression_timezone = var.frontend_timezone

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.frontend_scheduler.arn

    input = jsonencode({
      InstanceIds = [aws_instance.frontend.id]
    })
  }
}
