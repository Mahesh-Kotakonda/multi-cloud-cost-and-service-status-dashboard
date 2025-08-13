variable "project_name" {
  type        = string
  description = "Project name for tagging"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where ALB will be deployed"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs for ALB"
}



