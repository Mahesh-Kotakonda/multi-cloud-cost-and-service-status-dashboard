output "db_instance_endpoint" {
  value       = aws_db_instance.app_db.endpoint
  description = "RDS instance endpoint"
}

output "db_instance_id" {
  value       = aws_db_instance.app_db.id
  description = "RDS instance ID"
}
