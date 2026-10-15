variable "region" {
  type    = string
  default = "us-east-1"
}

variable "profile" {
  type    = string
  default = "user_cli"
}

variable "mode" {
  type        = string
  default     = "provisioned"
  description = "provisioned (db.t3.medium) o serverless (0,5 DCU mínimo)"
  validation {
    condition     = contains(["provisioned", "serverless"], var.mode)
    error_message = "mode debe ser provisioned o serverless."
  }
}

variable "my_ip_cidr" {
  type        = string
  description = "Tu IP pública en formato CIDR, p. ej. 190.1.2.3/32 (curl ifconfig.me)"
}

variable "public_key_path" {
  type    = string
  default = "~/.ssh/taller-docdb.pub"
}
