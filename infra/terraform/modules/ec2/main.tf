resource "aws_instance" "app" {
  count         = var.instance_count
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = var.subnet_ids[count.index]
  key_name      = var.key_name

  tags = {
    Name    = "${var.project_name}-app-${count.index + 1}"
    Project = var.project_name
  }
}
