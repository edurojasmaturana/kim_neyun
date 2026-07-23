# Registros DNS para verificar kimneyun.cl en Resend (proveedor de correo
# transaccional que reemplaza a SES tras el rechazo de production access).
# Los valores los entrega Resend al dar de alta el dominio; el DKIM es una clave
# pública (se publica en DNS por diseño, no es secreto). Región de Resend:
# sa-east-1 (São Paulo, la más cercana a Chile). "Enable Sending" activo;
# "Enable Receiving" no, porque el sistema solo envía. Conviven con los registros
# de SES (nombres distintos): ver ses.tf.

# API key de Resend (secreta): vive en SSM Parameter Store como SecureString,
# creada fuera de Terraform con `aws ssm put-parameter` para no exponerla en el
# repo ni en el state en texto plano en el código. Terraform la lee en apply-time
# y la inyecta como env var RESEND_API_KEY del Lambda API (ver api.tf).
data "aws_ssm_parameter" "resend_api_key" {
  name = "/kim-neyun/resend-api-key"
}

# DKIM: verifica el dominio y firma los correos salientes.
resource "aws_route53_record" "resend_dkim" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "resend._domainkey.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = ["p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCwC1G9AwQEYpb+0rRhGLjGvXCvRCtS4jCok2ptQ1VOaa64utGzBBYUxgyPxf06fXbJxaFlrlSFTK0XsAkscrsA4ztQo4a2R4diygDXOc/7lXZL3DILyFlxz4HOfFXSPgkNUn+yD2Ki+E/7pNYjX5MgphUuYjYUjmzMU0TYYnhaewIDAQAB"]
}

# SPF: return-path / manejo de rebotes en el subdominio send.kimneyun.cl.
resource "aws_route53_record" "resend_spf_mx" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "send.${var.domain_name}"
  type    = "MX"
  ttl     = 300
  records = ["10 feedback-smtp.sa-east-1.amazonses.com"]
}

resource "aws_route53_record" "resend_spf_txt" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "send.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = ["v=spf1 include:amazonses.com ~all"]
}

# DMARC (opcional, solo monitoreo con p=none).
resource "aws_route53_record" "resend_dmarc" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "_dmarc.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = ["v=DMARC1; p=none;"]
}
