terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 5.60" }
  }
}

provider "aws" {
  region  = var.region
  profile = var.profile
  default_tags {
    tags = { Proyecto = "taller-aws", Punto = "3" }
  }
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# ---- Llave SSH (solo se sube la parte PÚBLICA) ----
resource "aws_key_pair" "tunel" {
  key_name   = "taller-docdb-tunel"
  public_key = file(pathexpand(var.public_key_path))
}

# ---- Grupos de seguridad ----
resource "aws_security_group" "bastion" {
  name        = "taller-docdb-bastion"
  description = "EC2 puente: SSH solo desde mi IP"
  vpc_id      = data.aws_vpc.default.id
  ingress {
    description = "SSH desde mi IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "docdb" {
  name        = "taller-docdb"
  description = "DocumentDB: 27017 solo desde la EC2 puente"
  vpc_id      = data.aws_vpc.default.id
  ingress {
    description     = "MongoDB wire protocol desde la EC2"
    from_port       = 27017
    to_port         = 27017
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
  }
}

# ---- EC2 puente (t3.micro, misma VPC) ----
resource "aws_instance" "bastion" {
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = "t3.micro"
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.bastion.id]
  key_name                    = aws_key_pair.tunel.key_name
  associate_public_ip_address = true
  tags                        = { Name = "taller-docdb-bastion" }
}

# ---- DocumentDB ----
resource "aws_docdb_subnet_group" "this" {
  name       = "taller-docdb"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_docdb_cluster" "this" {
  cluster_identifier              = "taller-docdb"
  engine                          = "docdb"
  engine_version                  = "5.0.0"
  master_username                 = "docdbadmin"
  manage_master_user_password     = true # contraseña en Secrets Manager (no queda en el tfstate)
  db_subnet_group_name            = aws_docdb_subnet_group.this.name
  vpc_security_group_ids          = [aws_security_group.docdb.id]
  storage_encrypted               = true
  backup_retention_period         = 1 # mínimo permitido
  skip_final_snapshot             = true
  deletion_protection             = false

  dynamic "serverless_v2_scaling_configuration" {
    for_each = var.mode == "serverless" ? [1] : []
    content {
      min_capacity = 0.5
      max_capacity = 1
    }
  }
}

resource "aws_docdb_cluster_instance" "this" {
  identifier         = "taller-docdb-1"
  cluster_identifier = aws_docdb_cluster.this.id
  instance_class     = var.mode == "serverless" ? "db.serverless" : "db.t3.medium"
}
