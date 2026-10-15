terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = ">= 5.60" }
  }
}

provider "aws" {
  region  = var.region
  profile = var.profile # perfil user_cli, nunca la cuenta raíz
  default_tags {
    tags = { Proyecto = "taller-aws", Punto = "2", Metodo = "terraform" }
  }
}

data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# AMI más reciente de Amazon Linux 2023 (parámetro público de SSM)
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# ---------- 1) S3 ----------
resource "aws_s3_bucket" "demo" {
  bucket        = "taller-aws-tf-${data.aws_caller_identity.current.account_id}-${var.region}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "demo" {
  bucket                  = aws_s3_bucket.demo.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------- Red ----------
resource "aws_security_group" "ec2" {
  name        = "taller-aws-tf-ec2"
  description = "EC2 del taller (sin entradas abiertas)"
  vpc_id      = data.aws_vpc.default.id
  # Sin reglas de entrada: no hace falta SSH para el ejercicio.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name        = "taller-aws-tf-rds"
  description = "RDS: solo acepta trafico del SG de la EC2"
  vpc_id      = data.aws_vpc.default.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }
}

# ---------- 2) EC2 ----------
resource "aws_instance" "demo" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.ec2_type # t3.micro: de las más baratas con x86
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.ec2.id]
  root_block_device {
    volume_size = 8
    volume_type = "gp3"
  }
  tags = { Name = "taller-aws-tf" }
}

# ---------- 3) RDS (contraseña administrada por Secrets Manager) ----------
resource "aws_db_subnet_group" "demo" {
  name       = "taller-aws-tf"
  subnet_ids = data.aws_subnets.default.ids # RDS exige >= 2 zonas de disponibilidad
}

resource "aws_db_instance" "demo" {
  identifier             = "taller-aws-tf"
  engine                 = "postgres"
  engine_version         = var.pg_version
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  storage_type           = "gp3"
  db_name                = "taller"
  username               = "taller_admin"
  db_subnet_group_name   = aws_db_subnet_group.demo.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = false
  backup_retention_period = 0     # sin backups automáticos = sin snapshots que cobrar
  skip_final_snapshot    = true    # al destruir no deja snapshot facturable
  deletion_protection    = false

  # La contraseña la genera y guarda RDS en Secrets Manager.
  # Terraform NO conoce la contraseña, así que no queda en el archivo de estado.
  manage_master_user_password = true
}
