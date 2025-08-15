terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.4.0"

  backend "s3" {
    bucket         = "multi-cloud-cost-and-service-status-dashboard"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    use_lockfile   = true
  }
}

provider "aws" {
  region = var.aws_region
}

# ===== Fetch database credentials from AWS SSM Parameter Store =====
data "aws_ssm_parameter" "db_creds" {
  name            = "myapp_database_credentials"
  with_decryption = true
}

locals {
  db_creds = jsondecode(data.aws_ssm_parameter.db_creds.value)
}

# ===== VPC =====
module "vpc" {
  source               = "./modules/vpc"
  name                 = var.project_name
  project              = var.project_name
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  azs                  = var.azs
}

# ===== Security =====
module "security" {
  source       = "./modules/security"
  project_name = var.project_name
  vpc_id       = module.vpc.vpc_id
}

# ===== EC2 =====
module "ec2" {
  source            = "./modules/ec2"
  project_name      = var.project_name
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  security_group_id = module.security.ec2_sg_id
  ami_id            = var.ec2_ami
  instance_type     = var.ec2_instance_type
  key_name          = var.ec2_key_name
  instance_count    = var.instance_count
}

# ===== ALB =====
module "alb" {
  source              = "./modules/alb"
  project_name        = var.project_name
  vpc_id              = module.vpc.vpc_id
  public_subnet_ids   = module.vpc.public_subnet_ids
  security_group_id   = module.security.alb_sg_id
  target_instance_ids = module.ec2.instance_ids
}

# ===== Database =====
module "database" {
  source            = "./modules/database"
  project_name      = var.project_name
  db_instance_class = var.db_instance_class
  db_name           = var.db_name
  db_username       = local.db_creds.username
  db_password       = local.db_creds.password
  subnet_ids        = module.vpc.private_subnet_ids
}

# ===== Outputs =====
output "vpc_id" {
  value = module.vpc.vpc_id
}

output "public_subnet_ids" {
  value = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

output "ec2_instance_ids" {
  value = module.ec2.instance_ids
}

output "alb_dns" {
  value = module.alb.alb_dns
}

output "db_endpoint" {
  value = module.database.db_instance_endpoint
}
