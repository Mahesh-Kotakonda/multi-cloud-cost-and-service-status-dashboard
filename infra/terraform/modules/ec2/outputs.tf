output "instance_ids" {
  value       = aws_instance.app[*].id
  description = "IDs of the EC2 instances"
}

output "public_ips" {
  value       = aws_instance.app[*].public_ip
  description = "Public IPs of the EC2 instances"
}
