#!/bin/sh
set -e

mkdir -p /etc/selfsigned/ssl

openssl req -x509 -nodes -days 750 -newkey rsa:2048 \
  -keyout /etc/selfsigned/ssl/tls.key \
  -out /etc/selfsigned/ssl/tls.crt \
  -subj "/C=US/ST=Local/L=Docker/O=App/CN=internal"

# allow nonroot user to read certificates
chmod 644 /etc/selfsigned/ssl/tls.crt
chmod 644 /etc/selfsigned/ssl/tls.key