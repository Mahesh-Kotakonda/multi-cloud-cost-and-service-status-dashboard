variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "instance_count" {
  description = "Number of EC2 instances to create"
  type        = number
  # default     = 2
}

variable "project_name" {
  description = "Project name for tags"
  type        = string
}

# VPC
variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block"
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "Public subnet CIDRs"
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "Private subnet CIDRs"
}

variable "azs" {
  type        = list(string)
  description = "Availability zones"
}

# EC2
variable "ec2_ami" {
  type        = string
  description = "AMI ID for EC2"
}

variable "ec2_instance_type" {
  type        = string
  description = "EC2 instance type"
}

variable "ec2_key_name" {
  type        = string
  description = "Key pair name for EC2"
}

# Database (non-sensitive only)
variable "db_instance_class" {
  type        = string
  description = "RDS instance class"
}

variable "db_name" {
  type        = string
  description = "Database name"
}
