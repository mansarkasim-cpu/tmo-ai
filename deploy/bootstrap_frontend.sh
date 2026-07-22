#!/usr/bin/env bash
set -euo pipefail

# Bootstrap script to deploy frontend and configure Nginx
# Run as root or with sudo on the server.

FRONTEND_SRC="/opt/tmo-ai/frontend"
WWW_ROOT="/var/www/tmo-ai"
NGINX_SITE="/etc/nginx/conf.d/tmo-ai.conf"

echo "Creating web root: ${WWW_ROOT}"
mkdir -p "${WWW_ROOT}"

echo "Copying frontend files from ${FRONTEND_SRC}"
rsync -a --delete "${FRONTEND_SRC}/" "${WWW_ROOT}/"

echo "Setting ownership to tmoai:tmoai"
chown -R tmoai:tmoai "${WWW_ROOT}"
chmod -R 750 "${WWW_ROOT}"

echo "Installing nginx if missing (Debian/Ubuntu or RHEL/CentOS/Alma)":
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y nginx
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y nginx
elif command -v yum >/dev/null 2>&1; then
  yum install -y nginx
else
  echo "Package manager not detected — ensure nginx is installed manually." >&2
fi

echo "Deploying Nginx site configuration"
if [ -f "${PWD}/deploy/nginx/tmo-ai.conf" ]; then
  cp "${PWD}/deploy/nginx/tmo-ai.conf" "${NGINX_SITE}"
  sed -i "s/your.domain.tld/REPLACE_WITH_YOUR_DOMAIN/g" "${NGINX_SITE}"
else
  echo "Cannot find deploy/nginx/tmo-ai.conf in current directory. Copy it manually." >&2
fi

echo "Enabling and restarting nginx"
systemctl enable --now nginx || true
systemctl restart nginx

echo "Reloading systemd (frontend deployed)"
systemctl daemon-reload || true

echo "Bootstrap frontend complete.\n - Web root: ${WWW_ROOT}\n - Nginx site: ${NGINX_SITE}\nPlease replace 'REPLACE_WITH_YOUR_DOMAIN' in the Nginx config with your domain and run certbot for HTTPS."
