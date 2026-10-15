output "docdb_endpoint" {
  value = aws_docdb_cluster.this.endpoint
}

output "docdb_secret_arn" {
  value = aws_docdb_cluster.this.master_user_secret[0].secret_arn
}

output "bastion_public_ip" {
  value = aws_instance.bastion.public_ip
}
