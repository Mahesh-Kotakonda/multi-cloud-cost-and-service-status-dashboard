# In ./modules/alb/variables.tf

variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "vpc_id" {
  description = "The ID of the VPC to deploy the ALB into"
  type        = string
}

variable "public_subnet_ids" {
  description = "A list of public subnet IDs for the ALB"
  type        = list(string)
}

variable "security_group_id" {
  description = "The ID of the security group for the ALB"
  type        = string
}

variable "target_instance_ids" {
  description = "A list of EC2 instance IDs to attach to the target group"
  type        = list(string)
}
