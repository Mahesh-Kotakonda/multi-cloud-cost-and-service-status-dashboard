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
# Target Groups - Blue & Green (Frontend & Backend)
#########################################
# Frontend Blue
resource "aws_lb_target_group" "frontend_blue_tg" {
  name     = "${substr(var.project_name, 0, 16)}-fe-blue-tg"
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
}

# Frontend Green
resource "aws_lb_target_group" "frontend_green_tg" {
  name     = "${substr(var.project_name, 0, 16)}-fe-green-tg"
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
}

# Backend Blue
resource "aws_lb_target_group" "backend_blue_tg" {
  name     = "${substr(var.project_name, 0, 16)}-be-blue-tg"
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
}

# Backend Green
resource "aws_lb_target_group" "backend_green_tg" {
  name     = "${substr(var.project_name, 0, 16)}-be-green-tg"
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
}

#########################################
# Listener & Routing
#########################################
resource "aws_lb_listener" "app_listener" {
  load_balancer_arn = aws_lb.app_alb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend_blue_tg.arn
  }
}

# Backend API: /api/aws/* → backend blue
resource "aws_lb_listener_rule" "backend_blue_rule" {
  listener_arn = aws_lb_listener.app_listener.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend_blue_tg.arn
  }

  condition {
    path_pattern {
      values = ["/api/aws/*"]
    }
  }
}

# Frontend root "/" → frontend blue
resource "aws_lb_listener_rule" "frontend_blue_rule" {
  listener_arn = aws_lb_listener.app_listener.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend_blue_tg.arn
  }

  condition {
    path_pattern {
      values = ["/"]
    }
  }
}

#########################################
# Attach EC2 Instances to Target Groups
#########################################
# Frontend Blue
resource "aws_lb_target_group_attachment" "frontend_blue_attach" {
  count            = length(var.target_instance_ids)
  target_group_arn = aws_lb_target_group.frontend_blue_tg.arn
  target_id        = var.target_instance_ids[count.index]
  port             = 3000
}

# Frontend Green
resource "aws_lb_target_group_attachment" "frontend_green_attach" {
  count            = length(var.target_instance_ids)
  target_group_arn = aws_lb_target_group.frontend_green_tg.arn
  target_id        = var.target_instance_ids[count.index]
  port             = 3001
}

# Backend Blue
resource "aws_lb_target_group_attachment" "backend_blue_attach" {
  count            = length(var.target_instance_ids)
  target_group_arn = aws_lb_target_group.backend_blue_tg.arn
  target_id        = var.target_instance_ids[count.index]
  port             = 8080
}

# Backend Green
resource "aws_lb_target_group_attachment" "backend_green_attach" {
  count            = length(var.target_instance_ids)
  target_group_arn = aws_lb_target_group.backend_green_tg.arn
  target_id        = var.target_instance_ids[count.index]
  port             = 8081
}
