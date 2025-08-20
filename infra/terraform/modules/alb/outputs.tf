# ----------------------------
# ALB Outputs
# ----------------------------
output "alb_arn" {
  value       = aws_lb.app_alb.arn
  description = "ARN of the Application Load Balancer"
}

output "alb_dns" {
  value       = aws_lb.app_alb.dns_name
  description = "DNS name of the Application Load Balancer"
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


