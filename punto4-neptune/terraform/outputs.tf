output "neptune_endpoint" {
  value = aws_neptune_cluster.this.endpoint
}

output "bastion_public_ip" {
  value = aws_instance.bastion.public_ip
}
