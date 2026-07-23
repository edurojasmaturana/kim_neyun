# SES: identidad de dominio + registros DKIM en Route53 + permiso IAM al Lambda.
#
# CAVEAT DE SANDBOX: en sandbox SES solo envía a direcciones verificadas.
# Para enviar a cualquier email solicitar "Production access" en la consola SES.

# Identidad de dominio SES con Easy DKIM (RSA 2048).
resource "aws_sesv2_email_identity" "domain" {
  email_identity = var.domain_name

  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }

  tags = local.tags
}

# 3 registros CNAME de DKIM en Route53 (los genera AWS al crear la identidad).
# Referencia directa al recurso de dns.tf — no data source, para que funcione
# en un apply desde cero sin que la zona pre-exista.
resource "aws_route53_record" "ses_dkim" {
  count   = 3
  zone_id = aws_route53_zone.main.zone_id
  name    = "${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.domain_name}"
  type    = "CNAME"
  ttl     = 300
  records = ["${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

# MAIL FROM personalizado: usa "no-reply.<dominio>" como dominio del envelope
# (Return-Path), de modo que el SPF quede alineado con el dominio propio en vez
# del de amazonses.com (mejor deliverability y DMARC-friendly). Requiere un MX al
# endpoint de feedback de SES en la región y un TXT SPF. Si el MX falla, SES cae
# al MAIL FROM por defecto (USE_DEFAULT_VALUE) — no bloquea el envío.
resource "aws_sesv2_email_identity_mail_from_attributes" "domain" {
  email_identity         = aws_sesv2_email_identity.domain.email_identity
  mail_from_domain       = "no-reply.${var.domain_name}"
  behavior_on_mx_failure = "USE_DEFAULT_VALUE"
}

resource "aws_route53_record" "mail_from_mx" {
  zone_id = aws_route53_zone.main.zone_id
  name    = aws_sesv2_email_identity_mail_from_attributes.domain.mail_from_domain
  type    = "MX"
  ttl     = 300
  records = ["10 feedback-smtp.${var.region}.amazonses.com"]
}

resource "aws_route53_record" "mail_from_spf" {
  zone_id = aws_route53_zone.main.zone_id
  name    = aws_sesv2_email_identity_mail_from_attributes.domain.mail_from_domain
  type    = "TXT"
  ttl     = 300
  records = ["v=spf1 include:amazonses.com ~all"]
}

# Permiso para que el Lambda API envíe emails desde el dominio verificado.
data "aws_iam_policy_document" "api_ses" {
  statement {
    sid     = "SendEmail"
    actions = ["ses:SendEmail"]
    resources = [
      aws_sesv2_email_identity.domain.arn,
    ]
  }
}

resource "aws_iam_role_policy" "api_ses" {
  name   = "${local.name}-api-ses"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_ses.json
}
