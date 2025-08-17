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
# Target Group Outputs
# ----------------------------
output "frontend_target_group_arn" {
  value       = aws_lb_target_group.frontend_tg.arn
  description = "ARN of the frontend target group (port 3000)"
}

output "backend_target_group_arn" {
  value       = aws_lb_target_group.backend_tg.arn
  description = "ARN of the backend target group (port 8080)"
}
