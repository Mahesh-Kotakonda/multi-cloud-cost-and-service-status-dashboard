resource "aws_db_subnet_group" "db_subnets" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = var.subnet_ids

  tags = {
    Name    = "${var.project_name}-db-subnet-group"
    Project = var.project_name
  }
}

resource "aws_db_instance" "app_db" {
  identifier               = "${var.project_name}-db"
  engine                   = "mysql"
  instance_class           = var.db_instance_class
  allocated_storage        = var.allocated_storage
  # This is the correct argument for the database name within the instance
  db_name                  = var.db_name 
  username                 = var.db_username
  password                 = var.db_password
  db_subnet_group_name     = aws_db_subnet_group.db_subnets.name
  publicly_accessible      = false
  skip_final_snapshot      = true

  tags = {
    Name    = "${var.project_name}-db"
    Project = var.project_name
  }
}




