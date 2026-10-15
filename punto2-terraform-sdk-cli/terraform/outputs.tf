output "bucket" {
  value = aws_s3_bucket.demo.bucket
}

output "ec2_instance_id" {
  value = aws_instance.demo.id
}

output "rds_endpoint" {
  value = aws_db_instance.demo.address
}

# ARN del secreto (no su contenido) creado y administrado por RDS
output "rds_secret_arn" {
  value = aws_db_instance.demo.master_user_secret[0].secret_arn
}
