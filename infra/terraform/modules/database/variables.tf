variable "project_name" {
  type        = string
  description = "Project name for tagging"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets for RDS instance"
}

variable "db_instance_class" {
  type        = string
  default     = "db.t3.micro"
  description = "RDS instance type"
}

variable "allocated_storage" {
  type        = number
  default     = 20
  description = "Storage size in GB"
}

variable "db_name" {
  type        = string
  description = "Database name"
}

variable "db_username" {
  type        = string
  description = "Database username"
}

variable "db_password" {
  type        = string
  description = "Database password"
  sensitive   = true
}
