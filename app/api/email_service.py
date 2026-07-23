"""Envío de emails transaccionales vía Resend (https://resend.com).

Diseño «best-effort»: si Resend no está configurado (RESEND_API_KEY o
SES_FROM_EMAIL vacíos) o si la llamada falla, se loggea el error pero NO se
propaga — el endpoint de invitación igual devuelve el link para que el flujo no
quede bloqueado.

Se migró de AWS SES a Resend porque AWS denegó el production access de la cuenta
nueva dos veces (respuesta genérica). El volumen es bajísimo (transaccional), así
que Resend cubre de sobra con su tier gratuito y una verificación de dominio
inmediata. Se usa la API HTTP con urllib de la stdlib para no sumar dependencias.
"""

import json
import logging
import urllib.error
import urllib.request

from shared import config

logger = logging.getLogger("kim.email")

_RESEND_ENDPOINT = "https://api.resend.com/emails"

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
    """Envía el correo de invitación vía Resend.

    Devuelve True si se envió correctamente, False si Resend no está configurado
    o si ocurrió un error (el error se loggea pero no se propaga).
    """
    from_email = config.SES_FROM_EMAIL
    api_key = config.RESEND_API_KEY
    if not from_email or not api_key:
        logger.warning(
            "Envío de correo deshabilitado (falta RESEND_API_KEY o SES_FROM_EMAIL); "
            "se omite el correo a %s", to_email
        )
        return False

    ttl_hours = config.INVITATION_TTL_HOURS
    html_body = _HTML_TEMPLATE.format(
        invited_by=invited_by, role=role, link=link, ttl_hours=ttl_hours
    )
    text_body = _TEXT_TEMPLATE.format(
        invited_by=invited_by, role=role, link=link, ttl_hours=ttl_hours
    )

    payload = json.dumps({
        "from": f"KIM-NEYÜN <{from_email}>",
        "to": [to_email],
        "subject": _SUBJECT,
        "html": html_body,
        "text": text_body,
    }).encode("utf-8")

    request = urllib.request.Request(
        _RESEND_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            body = resp.read().decode("utf-8")
        message_id = json.loads(body).get("id") if body else None
        logger.info("Correo de invitación enviado a %s (id=%s)", to_email, message_id)
        return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        logger.error(
            "Error Resend enviando correo a %s: HTTP %s %s", to_email, exc.code, detail
        )
        return False
    except Exception as exc:
        logger.error("Error inesperado enviando correo a %s: %s", to_email, exc)
        return False
