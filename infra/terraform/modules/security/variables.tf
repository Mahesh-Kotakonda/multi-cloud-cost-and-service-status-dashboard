variable "project_name" {
  type        = string
  description = "Project name for tagging"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where security groups will be created"
}

variable "db_security_group_id" {
  description = "The ID of the security group for the db"
  type        = string
}
