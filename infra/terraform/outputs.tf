# VPC outputs
output "vpc_id" {
  value = module.vpc.vpc_id
}

output "public_subnet_ids" {
  value = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

# EC2 outputs
output "ec2_instance_ids" {
  value = module.ec2.instance_ids
}

# ALB outputs
output "alb_dns" {
  value = module.alb.alb_dns
}

# Database outputs
output "db_endpoint" {
  value = module.database.db_instance_endpoint
}
