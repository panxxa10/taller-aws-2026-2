#!/usr/bin/env bash
# Punto 1 - Comandos para reproducir. Ejecutar paso a paso (no como script ciego).
set -euo pipefail
export AWS_REGION=${AWS_REGION:-us-east-1}
SECRET=taller/punto1/credenciales-prueba
POLICY=PoliticaLecturaSecretoPunto1
APP_USER=app_lectora_punto1

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "== 1. Crear el secreto (usuario y contraseña ficticios) =="
aws secretsmanager create-secret --name "$SECRET" \
  --description "Secreto de prueba - taller AWS punto 1" \
  --secret-string '{"username":"usuario_demo","password":"Clave-Ficticia-v1"}' \
  --tags Key=Proyecto,Value=taller-aws

echo "== 2. Usuario de aplicación con permiso SOLO sobre ese secreto =="
sed "s/<ACCOUNT_ID>/$ACCOUNT_ID/" policy_lectura_secreto.json > /tmp/policy_punto1.json
aws iam create-user --user-name "$APP_USER"
aws iam put-user-policy --user-name "$APP_USER" --policy-name "$POLICY" \
  --policy-document file:///tmp/policy_punto1.json
aws iam create-access-key --user-name "$APP_USER"   # guardar en un perfil local: aws configure --profile app_lectora
# NO publicar la salida de este comando.

echo "== 3. Ejecutar el programa con el usuario restringido =="
echo "   AWS_PROFILE=app_lectora python secrets_demo.py --watch 5"

echo "== 4. Prueba de que NO puede leer otros secretos =="
echo "   AWS_PROFILE=app_lectora aws secretsmanager get-secret-value --secret-id otro/secreto   # -> AccessDenied"

echo "== 5. Modificar el valor (nueva versión, el código no cambia) =="
aws secretsmanager put-secret-value --secret-id "$SECRET" \
  --secret-string '{"username":"usuario_demo","password":"Clave-Ficticia-v2"}'
aws secretsmanager list-secret-version-ids --secret-id "$SECRET"

echo "== 6. Limpieza (evidencia de eliminación) =="
aws secretsmanager delete-secret --secret-id "$SECRET" --force-delete-without-recovery
aws iam delete-user-policy --user-name "$APP_USER" --policy-name "$POLICY"
# borrar la access key creada: aws iam list-access-keys / delete-access-key
aws iam delete-user --user-name "$APP_USER"
aws secretsmanager list-secrets --query "SecretList[].Name"   # debe quedar vacío
