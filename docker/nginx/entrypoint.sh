#!/bin/sh
set -e

HTTP_PORT=${HTTP_PORT:-80}
HTTPS_PORT=${HTTPS_PORT:-443}
SSL_CN=${SSL_CN:-localhost}
TEMPLATE=${NGINX_TEMPLATE:-/etc/nginx/templates/default.conf.template}

# ---------------------------------------------------------------------------
# SSL certificate
# If cert.pem / key.pem already exist (mounted from outside), use them.
# Otherwise generate a self-signed cert. Replace the generated files with
# a real cert at any time — just restart the container.
# ---------------------------------------------------------------------------
SSL_DIR=/etc/nginx/ssl
mkdir -p "$SSL_DIR"

if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
    echo "[proxy] No SSL certificate found — generating self-signed cert (CN=$SSL_CN)..."
    openssl req -x509 -newkey rsa:4096 \
        -keyout "$SSL_DIR/key.pem" \
        -out   "$SSL_DIR/cert.pem" \
        -days  365 \
        -nodes \
        -subj  "/CN=$SSL_CN" 2>/dev/null
    echo "[proxy] Self-signed certificate written to $SSL_DIR"
    echo "[proxy] To use a real cert: replace cert.pem and key.pem, then restart this container."
else
    echo "[proxy] SSL certificate found at $SSL_DIR — using existing cert."
fi

# ---------------------------------------------------------------------------
# Render nginx config from template.
# Only ${HTTP_PORT} and ${HTTPS_PORT} are substituted — nginx's own variables
# ($host, $http_upgrade, $remote_addr, etc.) are left untouched.
# ---------------------------------------------------------------------------
export HTTP_PORT HTTPS_PORT
envsubst '${HTTP_PORT} ${HTTPS_PORT}' < "$TEMPLATE" > /etc/nginx/conf.d/default.conf

echo "[proxy] nginx config rendered (HTTP=$HTTP_PORT → HTTPS=$HTTPS_PORT)"

exec nginx -g "daemon off;"
