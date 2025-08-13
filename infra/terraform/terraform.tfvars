aws_region           = "us-east-1"
name                 = "dev"
project              = "multi-cloud-cost-and-service-status-dashboard"

vpc_cidr             = "10.0.0.0/16"

public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.11.0/24", "10.0.12.0/24"]

azs                  = ["us-east-1a", "us-east-1b"]
