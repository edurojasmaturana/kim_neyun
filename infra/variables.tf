variable "region" {
  type        = string
  default     = "us-east-1"
  description = "Región AWS (la más barata de América)."
}

variable "project" {
  type        = string
  default     = "kim-neyun"
  description = "Prefijo de nombres de recursos."
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "Tag de las imágenes en ECR (api/inference/frontend)."
}

variable "batch_schedule" {
  type        = string
  default     = "cron(0 9 ? * MON *)"
  description = "EventBridge Scheduler para el job batch (lunes 09:00 hora Chile)."
}

variable "batch_timezone" {
  type    = string
  default = "America/Santiago"
}

variable "anios_proyeccion" {
  type        = string
  default     = "2024,2025,2026"
  description = "Años para los que el job precomputa la proyección anual."
}

variable "alerta_threshold" {
  type    = number
  default = 150
}

variable "batch_memory" {
  type    = number
  default = 3008
  # TEMPORAL: cuentas AWS nuevas (creadas <24h) tienen un límite antifraude de
  # 3008MB para memoria de Lambda (normal: 10240MB). Subir a 8192 cuando la
  # cuenta "envejezca" (~24h) y re-aplicar. Ver CHECKPOINT.md.
  description = "Memoria de la Lambda batch en MB (más memoria = más CPU)."
}

variable "batch_timeout" {
  type        = number
  default     = 900
  description = "Timeout de la Lambda batch en segundos (máx 900 = 15 min)."
}

variable "batch_ephemeral_mb" {
  type        = number
  default     = 4096
  description = "Almacenamiento /tmp de la Lambda batch en MB (para artefactos)."
}

variable "batch_backfill_full" {
  type        = bool
  default     = false
  description = "Si es true, el batch recalcula TODOS los años (incl. cerrados). Úsalo una vez tras corregir/ampliar el CSV histórico; déjalo en false para el run semanal incremental."
}

# --- Backend de usuarios (Aurora Serverless v2) ---

variable "aurora_engine_version" {
  type        = string
  default     = "16.6"
  description = "Versión de Aurora PostgreSQL (>= 16.3 para soportar min_capacity = 0)."
}

variable "aurora_database" {
  type        = string
  default     = "kim_users"
  description = "Nombre de la base de datos de usuarios."
}

variable "aurora_min_capacity" {
  type        = number
  default     = 0
  description = "ACUs mínimas. 0 = escala a cero (requiere provider AWS reciente). Usa 0.5 si tu provider no lo soporta."
}

variable "aurora_max_capacity" {
  type        = number
  default     = 1
  description = "ACUs máximas (1 ACU = 2 GB RAM). Sobra para una tabla de usuarios."
}

# --- Encendido/apagado programado del EC2 frontend (ahorro de costo) ---

variable "frontend_timezone" {
  type        = string
  default     = "America/Santiago"
  description = "Zona horaria de los schedules de encendido/apagado del dashboard."
}

variable "frontend_on_hour" {
  type        = number
  default     = 8
  description = "Hora (0-23, hora Chile) en que se ENCIENDE el EC2 del dashboard."
}

variable "frontend_off_hour" {
  type        = number
  default     = 20
  description = "Hora (0-23, hora Chile) en que se APAGA el EC2 del dashboard."
}

variable "frontend_schedule_days" {
  type        = string
  default     = "MON-FRI"
  description = "Días del schedule de encendido/apagado. \"MON-FRI\" (horario laboral) o \"*\" para todos los días (demos en fin de semana)."
}

variable "domain_name" {
  type        = string
  default     = "kimneyun.cl"
  description = "Dominio principal del proyecto. Usado en Route53 y en el Caddyfile del frontend."
}
