#!/usr/bin/env bash
#
# Crea cuentas miembro en AWS Organizations, una por entorno/proyecto,
# y espera a que cada una termine (create-account es asíncrono).
#
# Uso:
#   ./crear-cuentas.sh dev prod
#   PROYECTO=kim-neyun BASE_EMAIL=mb.us.94@gmail.com ./crear-cuentas.sh dev prod
#
set -euo pipefail

# --- Configuración (sobreescribible por variables de entorno) ---
PROYECTO="${PROYECTO:-kim-neyun}"
BASE_EMAIL="${BASE_EMAIL:-mb.us.94@gmail.com}"   # se usa con plus-addressing: usuario+algo@dominio
ENTORNOS=("$@")

if [ ${#ENTORNOS[@]} -eq 0 ]; then
  ENTORNOS=(dev prod)   # por defecto
fi

# Separa BASE_EMAIL en usuario + dominio para inyectar el "+sufijo"
EMAIL_USER="${BASE_EMAIL%@*}"
EMAIL_DOMAIN="${BASE_EMAIL#*@}"

echo "Proyecto:  $PROYECTO"
echo "Entornos:  ${ENTORNOS[*]}"
echo "Email base: $BASE_EMAIL"
echo

for ENV in "${ENTORNOS[@]}"; do
  ACCOUNT_NAME="${PROYECTO}-${ENV}"
  EMAIL="${EMAIL_USER}+${PROYECTO}-${ENV}@${EMAIL_DOMAIN}"

  echo "==> Creando cuenta: $ACCOUNT_NAME  <$EMAIL>"
  REQ_ID=$(aws organizations create-account \
    --email "$EMAIL" \
    --account-name "$ACCOUNT_NAME" \
    --query 'CreateAccountStatus.Id' \
    --output text)

  echo "    Request: $REQ_ID  (esperando...)"

  # Polling hasta que termine
  while true; do
    read -r STATE ACCOUNT_ID REASON <<<"$(aws organizations describe-create-account-status \
      --create-account-request-id "$REQ_ID" \
      --query 'CreateAccountStatus.[State,AccountId,FailureReason]' \
      --output text)"

    case "$STATE" in
      SUCCEEDED)
        echo "    ✅ $ACCOUNT_NAME  ->  AccountId: $ACCOUNT_ID"
        break
        ;;
      FAILED)
        echo "    ❌ $ACCOUNT_NAME  ->  FALLÓ: $REASON"
        break
        ;;
      *)
        sleep 5
        ;;
    esac
  done
  echo
done

echo "Listo. Para entrar a una cuenta hija:"
echo "  aws sts assume-role \\"
echo "    --role-arn arn:aws:iam::<ACCOUNT_ID>:role/OrganizationAccountAccessRole \\"
echo "    --role-session-name setup"
