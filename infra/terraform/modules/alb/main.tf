#########################################
# Application Load Balancer
#########################################
resource "aws_lb" "app_alb" {
  name               = "${substr(var.project_name, 0, 20)}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]
  subnets            = var.public_subnet_ids

  tags = {
    Name    = "${var.project_name}-alb"
    Project = var.project_name
  }
}

#########################################
# Target Groups
#########################################

# Frontend TG (port 3000)
resource "aws_lb_target_group" "frontend_tg" {
  name     = "${substr(var.project_name, 0, 16)}-fe-tg"
  port     = 3000
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    path                = "/"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
    matcher             = "200-399"
  }

  tags = {
    Name    = "${var.project_name}-frontend-tg"
    Project = var.project_name
  }
}

# Backend TG (port 8080)
resource "aws_lb_target_group" "backend_tg" {
  name     = "${substr(var.project_name, 0, 16)}-be-tg"
  port     = 8080
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    path                = "/docs"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
    matcher             = "200-399"
  }

  tags = {
    Name    = "${var.project_name}-backend-tg"
    Project = var.project_name
  }
}

#########################################
# Listener & Routing
#########################################
resource "aws_lb_listener" "app_listener" {
  load_balancer_arn = aws_lb.app_alb.arn
  port              = 80
  protocol          = "HTTP"

  # Default action → return 404 for any other paths
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Error: Invalid path"
      status_code  = "404"
    }
  }
}

# Rule 1: /api/aws/* → backend
resource "aws_lb_listener_rule" "backend_api_rule" {
  listener_arn = aws_lb_listener.app_listener.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend_tg.arn
  }

  condition {
    path_pattern {
      values = ["/api/aws/*"]
    }
  }
}

# Rule 2: / → frontend
resource "aws_lb_listener_rule" "frontend_root_rule" {
  listener_arn = aws_lb_listener.app_listener.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend_tg.arn
  }

  condition {
    path_pattern {
      values = ["/"]
    }
  }
}

#########################################
# Attach EC2 Instances
#########################################
resource "aws_lb_target_group_attachment" "frontend_attach" {
  count            = length(var.target_instance_ids)
  target_group_arn = aws_lb_target_group.frontend_tg.arn
  target_id        = var.target_instance_ids[count.index]
  port             = 3000
}

resource "aws_lb_target_group_attachment" "backend_attach" {
  count            = length(var.target_instance_ids)
  target_group_arn = aws_lb_target_group.backend_tg.arn
  target_id        = var.target_instance_ids[count.index]
  port             = 8080
}
