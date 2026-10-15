#!/usr/bin/env bash
# Punto 2 - Mismo despliegue con AWS CLI. Requiere AWS_PROFILE=user_cli
set -euo pipefail
export AWS_REGION=${AWS_REGION:-us-east-1}
TAGS_KV="Key=Proyecto,Value=taller-aws Key=Metodo,Value=cli"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="taller-aws-cli-${ACCOUNT}-${AWS_REGION}"
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text)
SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC" --query "Subnets[].SubnetId" --output text)
FIRST_SUBNET=$(echo "$SUBNETS" | awk '{print $1}')

echo "== S3 =="
aws s3api create-bucket --bucket "$BUCKET"   # us-east-1: sin LocationConstraint
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging 'TagSet=[{Key=Proyecto,Value=taller-aws},{Key=Metodo,Value=cli}]'

echo "== Red =="
SG_EC2=$(aws ec2 create-security-group --group-name taller-aws-cli-ec2 --description "EC2 taller" --vpc-id "$VPC" --query GroupId --output text)
SG_RDS=$(aws ec2 create-security-group --group-name taller-aws-cli-rds --description "RDS taller" --vpc-id "$VPC" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG_RDS" --protocol tcp --port 5432 --source-group "$SG_EC2"

echo "== EC2 =="
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)
aws ec2 run-instances --image-id "$AMI" --instance-type t3.micro --count 1 \
  --subnet-id "$FIRST_SUBNET" --security-group-ids "$SG_EC2" \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=8,VolumeType=gp3,DeleteOnTermination=true}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=taller-aws-cli},{Key=Proyecto,Value=taller-aws},{Key=Metodo,Value=cli}]' \
  --query "Instances[0].InstanceId" --output text

echo "== RDS (contraseña administrada en Secrets Manager) =="
# shellcheck disable=SC2086
aws rds create-db-subnet-group --db-subnet-group-name taller-aws-cli \
  --db-subnet-group-description "taller" --subnet-ids $SUBNETS
aws rds create-db-instance --db-instance-identifier taller-aws-cli \
  --engine postgres --db-instance-class db.t4g.micro \
  --allocated-storage 20 --storage-type gp3 --db-name taller \
  --master-username taller_admin --manage-master-user-password \
  --db-subnet-group-name taller-aws-cli --vpc-security-group-ids "$SG_RDS" \
  --no-publicly-accessible --no-multi-az --backup-retention-period 0 \
  --tags $TAGS_KV
aws rds wait db-instance-available --db-instance-identifier taller-aws-cli
aws rds describe-db-instances --db-instance-identifier taller-aws-cli \
  --query "DBInstances[0].[Endpoint.Address,MasterUserSecret.SecretArn]" --output text
