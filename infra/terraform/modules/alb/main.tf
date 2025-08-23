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
# Target Groups (Blue-Green)
#########################################

# Frontend Blue TG (port 3000)
resource "aws_lb_target_group" "frontend_blue_tg" {
  name     = "${substr(var.project_name, 0, 16)}-fe-blue"
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
    Name    = "${var.project_name}-frontend-blue-tg"
    Project = var.project_name
  }
}

# Frontend Green TG (port 3001)
resource "aws_lb_target_group" "frontend_green_tg" {
  name     = "${substr(var.project_name, 0, 16)}-fe-green"
  port     = 3001
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
    Name    = "${var.project_name}-frontend-green-tg"
    Project = var.project_name
  }
}

# Backend Blue TG (port 8080)
resource "aws_lb_target_group" "backend_blue_tg" {
  name     = "${substr(var.project_name, 0, 16)}-be-blue"
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
    Name    = "${var.project_name}-backend-blue-tg"
    Project = var.project_name
  }
}

# Backend Green TG (port 8081)
resource "aws_lb_target_group" "backend_green_tg" {
  name     = "${substr(var.project_name, 0, 16)}-be-green"
  port     = 8081
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
    Name    = "${var.project_name}-backend-green-tg"
    Project = var.project_name
  }
}

#########################################
# Listener (safe default only)
#########################################
resource "aws_lb_listener" "app_listener" {
  load_balancer_arn = aws_lb.app_alb.arn
  port              = 80
  protocol          = "HTTP"

  # Default action → safe 503 until workflow updates
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Service not ready - switch target group via workflow"
      status_code  = "503"
    }
  }
}
