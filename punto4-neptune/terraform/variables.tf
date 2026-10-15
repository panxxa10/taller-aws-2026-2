variable "region" {
  type    = string
  default = "us-east-1"
}

variable "profile" {
  type    = string
  default = "user_cli"
}

variable "mode" {
  type    = string
  default = "serverless"
  validation {
    condition     = contains(["provisioned", "serverless"], var.mode)
    error_message = "mode debe ser provisioned o serverless."
  }
}

variable "my_ip_cidr" {
  type        = string
  description = "Tu IP pública CIDR, p. ej. 190.1.2.3/32"
}

variable "public_key_path" {
  type    = string
  default = "~/.ssh/taller-neptune.pub"
}
