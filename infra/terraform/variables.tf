variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
}

variable "name" {
  description = "Name prefix for resources"
  type        = string
}

variable "project" {
  description = "Project name for tagging"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
}

variable "public_subnet_cidrs" {
  description = "List of public subnet CIDRs"
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "List of private subnet CIDRs"
  type        = list(string)
}

variable "azs" {
  description = "List of availability zones"
  type        = list(string)
}
