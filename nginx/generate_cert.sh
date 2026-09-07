#!/usr/bin/env bash
# 为 lalabots.com 生成自签名 SSL 证书（有效期 10 年）
# 用法（在服务器项目根目录执行）：bash nginx/generate_cert.sh
# 说明：使用 alpine/openssl 容器生成，服务器无需额外安装 openssl
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/certs"
mkdir -p "$CERT_DIR"

docker run --rm -v "$CERT_DIR:/certs" -w /certs alpine/openssl \
  req -x509 -nodes -newkey rsa:2048 -days 3650 \
  -keyout lalabots.com.key -out lalabots.com.crt \
  -subj "/CN=lalabots.com" \
  -addext "subjectAltName=DNS:lalabots.com,DNS:www.lalabots.com"

echo "证书已生成：$CERT_DIR/lalabots.com.crt 与 lalabots.com.key"
