resource "aws_instance" "app" {
  count         = var.instance_count
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = var.public_subnet_ids[count.index]
  key_name      = var.key_name

  vpc_security_group_ids = [var.security_group_id]

  # This is the key line to add the Docker installation script
  user_data = file("${path.module}/install_docker.sh")

  tags = {
    Name    = "${var.project_name}-app-${count.index + 1}"
    Project = var.project_name
  }
}
