#!/usr/bin/env bash
# Punto 2 - Eliminación de lo creado con deploy_cli.sh
set -uo pipefail
export AWS_REGION=${AWS_REGION:-us-east-1}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="taller-aws-cli-${ACCOUNT}-${AWS_REGION}"

aws rds delete-db-instance --db-instance-identifier taller-aws-cli --skip-final-snapshot --delete-automated-backups
aws rds wait db-instance-deleted --db-instance-identifier taller-aws-cli
aws rds delete-db-subnet-group --db-subnet-group-name taller-aws-cli

IDS=$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values=taller-aws-cli Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query "Reservations[].Instances[].InstanceId" --output text)
if [ -n "$IDS" ]; then
  # shellcheck disable=SC2086
  aws ec2 terminate-instances --instance-ids $IDS
  # shellcheck disable=SC2086
  aws ec2 wait instance-terminated --instance-ids $IDS
fi

for NAME in taller-aws-cli-rds taller-aws-cli-ec2; do
  GID=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$NAME" --query "SecurityGroups[0].GroupId" --output text)
  [ "$GID" != "None" ] && aws ec2 delete-security-group --group-id "$GID"
done

aws s3api delete-bucket --bucket "$BUCKET"
echo "Verifique: aws ec2 describe-instances / aws rds describe-db-instances / aws s3 ls / aws secretsmanager list-secrets"
