variable "region" {
  type    = string
  default = "us-east-1"
}

variable "profile" {
  type    = string
  default = "user_cli"
}

variable "ec2_type" {
  type    = string
  default = "t3.micro"
}

variable "pg_version" {
  type        = string
  default     = "16"
  description = "Versión mayor de PostgreSQL (RDS elige la menor disponible)."
}
