aws_region = "us-east-1"
project_name = "multi-cloud-dashboard"

vpc_cidr = "10.0.0.0/16"
public_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.3.0/24", "10.0.4.0/24"]
azs = ["us-east-1a", "us-east-1b"]

ec2_ami = "ami-0c94855ba95c71c99"
ec2_instance_type = "t3.micro"
ec2_key_name = "terraform_key"

db_instance_class = "db.t3.micro"
db_name = "appdb"
db_username = "admin"
db_password = "SuperSecret123!"
