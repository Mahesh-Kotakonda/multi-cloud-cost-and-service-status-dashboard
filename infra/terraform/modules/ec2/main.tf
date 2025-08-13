
resource "aws_instance" "app" {
  count         = var.instance_count
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = var.public_subnet_ids[count.index]
  key_name      = var.key_name

  # This is the key line. vpc_security_group_ids requires the VPC ID indirectly.
  # The security group you create in the security module is already tied to the VPC.
  vpc_security_group_ids = [var.security_group_id]

  tags = {
    Name    = "${var.project_name}-app-${count.index + 1}"
    Project = var.project_name
  }
}
