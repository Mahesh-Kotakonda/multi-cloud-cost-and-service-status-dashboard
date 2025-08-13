variable "instance_count" {
  description = "The number of EC2 instances to create."
  type        = number
}

variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "vpc_id" {
  description = "The ID of the VPC to deploy the EC2 instances into"
  type        = string
}

variable "public_subnet_ids" {
  description = "A list of public subnet IDs"
  type        = list(string)
}

variable "security_group_id" {
  description = "The ID of the security group for the EC2 instances"
  type        = string
}

variable "ami_id" {
  description = "The AMI ID for the EC2 instances"
  type        = string
}

variable "instance_type" {
  description = "The instance type for the EC2 instances"
  type        = string
}

variable "key_name" {
  description = "The key pair name for SSH access"
  type        = string
}


