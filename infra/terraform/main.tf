terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.4.0"
}

provider "aws" {
  region = var.aws_region
}

# Call VPC module
module "vpc" {
  source              = "./modules/vpc"
  project_name        = var.project_name
  vpc_cidr            = var.vpc_cidr
  public_subnet_cidrs = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  azs                 = var.azs
}

# Call Security module
module "security" {
  source       = "./modules/security"
  project_name = var.project_name
  vpc_id       = module.vpc.vpc_id
}

# Call EC2 module
module "ec2" {
  source            = "./modules/ec2"
  project_name      = var.project_name
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  security_group_id = module.security.ec2_sg_id
  ami_id            = var.ec2_ami
  instance_type     = var.ec2_instance_type
  key_name          = var.ec2_key_name
}

# Call ALB module
module "alb" {
  source            = "./modules/alb"
  project_name      = var.project_name
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  # security_group_id = module.security.alb_sg_id
  # target_instance_ids = module.ec2.instance_ids
}

# Call Database module
module "database" {
  source           = "./modules/database"
  project_name     = var.project_name
  db_instance_class = var.db_instance_class
  db_name          = var.db_name
  db_username      = var.db_username
  db_password      = var.db_password
  subnet_ids       = module.vpc.private_subnet_ids
  security_group_id = module.security.db_sg_id
}

