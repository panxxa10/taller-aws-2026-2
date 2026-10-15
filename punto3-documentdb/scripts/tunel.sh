#!/usr/bin/env bash
# Abre el túnel SSH: localhost:27017 -> (EC2 puente) -> DocumentDB:27017
# Uso: ./tunel.sh <IP_PUBLICA_EC2> <ENDPOINT_DOCDB> [ruta_llave]
set -euo pipefail
BASTION_IP=${1:?IP pública de la EC2}
DOCDB_ENDPOINT=${2:?endpoint del cluster DocumentDB}
KEY=${3:-$HOME/.ssh/taller-docdb}

# Certificado de confianza de AWS (necesario para TLS)
[ -f global-bundle.pem ] || curl -sSO https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

echo "Túnel abierto en localhost:27017. Deja esta terminal abierta."
exec ssh -i "$KEY" -N -L 27017:"$DOCDB_ENDPOINT":27017 ec2-user@"$BASTION_IP" \
  -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new
