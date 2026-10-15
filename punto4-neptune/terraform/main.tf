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
    tags = { Proyecto = "taller-aws", Punto = "4" }
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

resource "aws_key_pair" "tunel" {
  key_name   = "taller-neptune-tunel"
  public_key = file(pathexpand(var.public_key_path))
}

resource "aws_security_group" "bastion" {
  name        = "taller-neptune-bastion"
  description = "EC2 puente: SSH solo desde mi IP"
  vpc_id      = data.aws_vpc.default.id
  ingress {
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

resource "aws_security_group" "neptune" {
  name        = "taller-neptune"
  description = "Neptune: 8182 solo desde la EC2 puente"
  vpc_id      = data.aws_vpc.default.id
  ingress {
    from_port       = 8182
    to_port         = 8182
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
  }
}

resource "aws_instance" "bastion" {
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = "t3.micro"
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.bastion.id]
  key_name                    = aws_key_pair.tunel.key_name
  associate_public_ip_address = true
  tags                        = { Name = "taller-neptune-bastion" }
}

resource "aws_neptune_subnet_group" "this" {
  name       = "taller-neptune"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_neptune_cluster" "this" {
  cluster_identifier                   = "taller-neptune"
  engine                               = "neptune"
  neptune_subnet_group_name            = aws_neptune_subnet_group.this.name
  vpc_security_group_ids               = [aws_security_group.neptune.id]
  storage_encrypted                    = true
  iam_database_authentication_enabled  = false # laboratorio; ver README para habilitar SigV4
  backup_retention_period              = 1
  skip_final_snapshot                  = true
  deletion_protection                  = false

  dynamic "serverless_v2_scaling_configuration" {
    for_each = var.mode == "serverless" ? [1] : []
    content {
      min_capacity = 1   # NCU mínimas en versiones recientes (antes 2,5): verificar para la versión usada
      max_capacity = 2.5
    }
  }
}

resource "aws_neptune_cluster_instance" "this" {
  identifier         = "taller-neptune-1"
  cluster_identifier = aws_neptune_cluster.this.id
  instance_class     = var.mode == "serverless" ? "db.serverless" : "db.t4g.medium"
}
