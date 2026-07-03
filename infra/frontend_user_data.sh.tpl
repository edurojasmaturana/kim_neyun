#!/bin/bash
# Cloud-init: instala Docker, corre el dashboard Streamlit y un proxy Caddy
# (TLS autofirmado, soporta WebSocket -- App Runner NO soporta WebSocket y
# Streamlit lo requiere para _stcore/stream, ver CHECKPOINT.md).
set -euxo pipefail

dnf install -y docker
systemctl enable --now docker

for i in $(seq 1 30); do
  docker info >/dev/null 2>&1 && break
  sleep 1
done

REGISTRY="$(echo "${ecr_image}" | cut -d/ -f1)"
aws ecr get-login-password --region ${region} | docker login --username AWS --password-stdin "$REGISTRY"

docker network inspect kimnet >/dev/null 2>&1 || docker network create kimnet

docker pull "${ecr_image}"

docker rm -f frontend >/dev/null 2>&1 || true
docker run -d --name frontend --restart unless-stopped --network kimnet \
  -e API_BASE_URL="${api_base_url}" \
  "${ecr_image}"

mkdir -p /opt/caddy
cat > /opt/caddy/Caddyfile <<EOF
${domain_name} {
    reverse_proxy frontend:8501
}
EOF

docker rm -f caddy >/dev/null 2>&1 || true
docker run -d --name caddy --restart unless-stopped --network kimnet \
  -p 80:80 \
  -p 443:443 \
  -v /opt/caddy/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v caddy_data:/data \
  caddy:2
