# SES: identidad de dominio + registros DKIM en Route53 + permiso IAM al Lambda.
#
# PREREQUISITO: la zona Route53 para var.domain_name debe existir en AWS antes
# de aplicar este archivo (la crea infra/dns.tf, actualmente en PR #7). El data
# source de abajo la busca por nombre; si no existe, `terraform plan` falla con
# "no matching Route53 Hosted Zone found".
#
# CAVEAT DE SANDBOX: la cuenta SES 735252692369 está en sandbox (Production
# Access = false). En sandbox SES solo envía a direcciones de destino que estén
# verificadas en SES. Para enviar a cualquier email hay que solicitar
# "Production access" en la consola de SES (Account Dashboard → Request
# production access) — proceso manual que AWS aprueba en 24 h.

# Lookup de la zona Route53 existente (creada por infra/dns.tf).
data "aws_route53_zone" "ses_lookup" {
  name         = var.domain_name
  private_zone = false
}

# Identidad de dominio SES con Easy DKIM (RSA 2048).
resource "aws_sesv2_email_identity" "domain" {
  email_identity = var.domain_name

  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }

  tags = local.tags
}

# 3 registros CNAME de DKIM en Route53 (los genera AWS al crear la identidad).
resource "aws_route53_record" "ses_dkim" {
  count   = 3
  zone_id = data.aws_route53_zone.ses_lookup.zone_id
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
