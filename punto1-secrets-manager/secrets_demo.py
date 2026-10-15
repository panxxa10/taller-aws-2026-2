"""Punto 1 - Recupera un secreto de AWS Secrets Manager con Boto3.

El programa NO contiene credenciales: solo el NOMBRE del secreto.
Siempre pide la versión AWSCURRENT, así que si el valor se modifica
(put-secret-value) el programa obtiene el nuevo valor sin cambiar el código.

Uso:
    python secrets_demo.py            # una lectura
    python secrets_demo.py --watch 5  # lee cada 5 s (para evidenciar la actualización)
    python secrets_demo.py --cached   # usa caché en memoria (aws-secretsmanager-caching)
"""
import argparse
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "us-east-1")
SECRET_NAME = os.environ.get("SECRET_NAME", "taller/punto1/credenciales-prueba")


def mask(value: str) -> str:
    """Nunca imprimimos la contraseña completa (para que las capturas sean seguras)."""
    return value[:2] + "*" * (len(value) - 2) if len(value) > 2 else "**"


def get_secret(client):
    try:
        resp = client.get_secret_value(SecretId=SECRET_NAME)  # VersionStage=AWSCURRENT por defecto
    except ClientError as e:
        code = e.response["Error"]["Code"]
        raise SystemExit(f"No se pudo leer el secreto ({code}): {e.response['Error']['Message']}")
    data = json.loads(resp["SecretString"])
    return data, resp["VersionId"]


def show(data, version_id):
    print(f"[{time.strftime('%H:%M:%S')}] version={version_id[:8]}... "
          f"usuario={data['username']} password={mask(data['password'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", type=int, metavar="SEGUNDOS", help="releer cada N segundos")
    parser.add_argument("--cached", action="store_true", help="usar caché en memoria (TTL de 5 min)")
    args = parser.parse_args()

    client = boto3.client("secretsmanager", region_name=REGION)

    if args.cached:
        from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
        cache = SecretCache(config=SecretCacheConfig(secret_refresh_interval=300), client=client)
        getter = lambda: (json.loads(cache.get_secret_string(SECRET_NAME)), "cache")
    else:
        getter = lambda: get_secret(client)

    while True:
        data, version_id = getter()
        show(data, version_id)
        if not args.watch:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
