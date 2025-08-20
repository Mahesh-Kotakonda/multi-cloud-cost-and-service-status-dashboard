# Project metadata
output "project_name" {
  value = var.project_name
}



# ----------------------------
# Frontend Target Groups
# ----------------------------
output "frontend_blue_tg_arn" {
  value       = aws_lb_target_group.frontend_blue_tg.arn
  description = "ARN of the frontend blue target group (port 3000)"
}

output "frontend_green_tg_arn" {
  value       = aws_lb_target_group.frontend_green_tg.arn
  description = "ARN of the frontend green target group (port 3001)"
}

# ----------------------------
# Backend Target Groups
# ----------------------------
output "backend_blue_tg_arn" {
  value       = aws_lb_target_group.backend_blue_tg.arn
  description = "ARN of the backend blue target group (port 8080)"
}

output "backend_green_tg_arn" {
  value       = aws_lb_target_group.backend_green_tg.arn
  description = "ARN of the backend green target group (port 8081)"
}


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

output "db_instance_id" {
  value = module.database.db_instance_id
}
