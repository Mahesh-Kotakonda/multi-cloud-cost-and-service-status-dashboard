aws_region = "ap-south-1"
project_name = "multi-cloud-dashboard"

vpc_cidr = "10.0.0.0/16"
public_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.3.0/24", "10.0.4.0/24"]
azs = ["ap-south-1a", "ap-south-1b"]

ec2_instance_type = "t3.micro"
ec2_key_name = "multi-cloud-cost-and-services-status-dashboard-keypair"

db_instance_class = "db.t3.micro"
db_name = "appdb"
instance_count = 2
