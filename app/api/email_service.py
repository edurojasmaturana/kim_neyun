"""Envío de emails transaccionales vía AWS SES v2.

Diseño «best-effort»: si SES no está configurado (SES_FROM_EMAIL vacío) o
si la llamada falla, se loggea el error pero NO se propaga — el endpoint de
invitación igual devuelve el link para que el flujo no quede bloqueado.

Caveat de sandbox: en una cuenta SES nueva (sandbox), solo se puede enviar a
direcciones de destino verificadas en SES. Para enviar a cualquier email hay
que solicitar "Production access" (SES → Account Dashboard → Request production
access en la consola de AWS).
"""

import logging

import boto3
from botocore.exceptions import ClientError

from shared import config

logger = logging.getLogger("kim.email")

_SUBJECT = "Te invitaron a KIM-NEYÜN"

_HTML_TEMPLATE = """\
<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><title>Invitación KIM-NEYÚN</title></head>
<body style="font-family:system-ui,sans-serif;background:#f8fafc;margin:0;padding:2rem;">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;
            padding:2rem 2.5rem;box-shadow:0 4px 20px rgba(0,0,0,.08);">
  <h1 style="font-size:1.1rem;color:#0369a1;margin:0 0 .5rem;">KIM-NEYÜN</h1>
  <p style="color:#334155;font-size:.95rem;line-height:1.5;">
    <strong>{invited_by}</strong> te ha invitado a la plataforma de pronóstico de
    demanda asistencial <strong>KIM-NEYÚN</strong> con el rol <strong>{role}</strong>.
  </p>
  <p style="color:#334155;font-size:.95rem;line-height:1.5;">
    Haz clic en el botón para crear tu cuenta (el enlace caduca en
    {ttl_hours} horas y es de un solo uso):
  </p>
  <p style="text-align:center;margin:1.75rem 0;">
    <a href="{link}"
       style="background:#0369a1;color:#fff;padding:.7rem 1.6rem;border-radius:8px;
              text-decoration:none;font-weight:600;font-size:.95rem;">
      Crear mi cuenta
    </a>
  </p>
  <p style="color:#94a3b8;font-size:.8rem;word-break:break-all;">
    Si el botón no funciona, copia este enlace en tu navegador:<br>
    <a href="{link}" style="color:#0369a1;">{link}</a>
  </p>
</div>
</body>
</html>
"""

_TEXT_TEMPLATE = """\
Te invitaron a KIM-NEYÚN
=========================

{invited_by} te ha invitado a la plataforma con el rol "{role}".

Crea tu cuenta en el siguiente enlace (caduca en {ttl_hours} h, un solo uso):
{link}
"""


def send_invitation_email(to_email: str, link: str, role: str, invited_by: str) -> bool:
    """Envía el correo de invitación vía SES v2.

    Devuelve True si se envió correctamente, False si SES no está configurado
    o si ocurrió un error (el error se loggea pero no se propaga).
    """
    from_email = config.SES_FROM_EMAIL
    if not from_email:
        logger.warning(
            "SES_FROM_EMAIL no configurado; se omite el envío de correo a %s", to_email
        )
        return False

    ttl_hours = config.INVITATION_TTL_HOURS
    html_body = _HTML_TEMPLATE.format(
        invited_by=invited_by, role=role, link=link, ttl_hours=ttl_hours
    )
    text_body = _TEXT_TEMPLATE.format(
        invited_by=invited_by, role=role, link=link, ttl_hours=ttl_hours
    )

    try:
        client = boto3.client("sesv2", region_name=config.AWS_REGION)
        client.send_email(
            FromEmailAddress=from_email,
            Destination={"ToAddresses": [to_email]},
            Content={
                "Simple": {
                    "Subject": {"Data": _SUBJECT, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                    },
                }
            },
        )
        logger.info("Correo de invitación enviado a %s", to_email)
        return True
    except ClientError as exc:
        logger.error(
            "Error SES enviando correo a %s: %s", to_email, exc.response["Error"]["Message"]
        )
        return False
    except Exception as exc:
        logger.error("Error inesperado enviando correo a %s: %s", to_email, exc)
        return False
