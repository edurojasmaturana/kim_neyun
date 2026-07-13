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
