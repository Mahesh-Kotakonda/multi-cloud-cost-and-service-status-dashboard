output "alb_arn" {
  value       = aws_lb.app_alb.arn
  description = "ARN of the ALB"
}

output "target_group_arn" {
  value       = aws_lb_target_group.app_tg.arn
  description = "ARN of the Target Group"
}
output "alb_dns" {
  description = "The DNS name of the Application Load Balancer"
  value       = aws_lb.app_alb.dns_name
}
