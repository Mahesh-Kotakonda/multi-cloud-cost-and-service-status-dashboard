import os
import json
import boto3
import subprocess
import datetime
import paramiko

# Helper to run shell commands
def run_command(cmd):
    print(f"Running command: {cmd}")
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        print(f"Command failed: {result.stderr}")
        raise RuntimeError(f"Command failed: {cmd}")
    return result.stdout.strip()

# SSH and manage containers on instance
def deploy_on_instance(instance_ip, pem_path, container_name):
    print(f"Deploying {container_name} on instance {instance_ip}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(instance_ip, username="ec2-user", key_filename=pem_path)

    remove_cmd = f"docker rm -f {container_name} || true"
    stdin, stdout, stderr = ssh.exec_command(remove_cmd)
    err = stderr.read().decode().strip()
    if err:
        print(f"[{instance_ip}] Error removing old {container_name}: {err}")
    else:
        print(f"[{instance_ip}] Old {container_name} removed (if existed).")

    rename_cmd = f"docker rename {container_name}_new {container_name} || true"
    stdin, stdout, stderr = ssh.exec_command(rename_cmd)
    err = stderr.read().decode().strip()
    if err:
        print(f"[{instance_ip}] Error renaming {container_name}_new: {err}")
    else:
        print(f"[{instance_ip}] {container_name}_new renamed to {container_name}.")

    ssh.close()
    print(f"[{instance_ip}] {container_name} deployment completed.")

# Deploy containers across multiple instances
def deploy_containers(instance_ids, pem_path, container_name, aws_access_key, aws_secret_key, aws_region):
    if not instance_ids:
        print(f"[INFO] No instance IDs provided for {container_name}, skipping deployment.")
        return
    ec2 = boto3.client(
        "ec2",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )
    reservations = ec2.describe_instances(InstanceIds=instance_ids.split(","))["Reservations"]
    for res in reservations:
        for inst in res["Instances"]:
            public_ip = inst.get("PublicIpAddress")
            if public_ip:
                deploy_on_instance(public_ip, pem_path, container_name)
            else:
                print(f"[INFO] Skipping {container_name} deployment for instance {inst['InstanceId']}: No public IP available.")

# ALB rule management
def create_or_update_rule(listener_arn, path, target_group_arn, priority, service_name):
    if not target_group_arn:
        print(f"[INFO] Skipping ALB rule creation for {service_name} path '{path}': Target group ARN not found.")
        return
    print(f"Processing ALB rule for {service_name}: path='{path}' -> TG='{target_group_arn}'")
    rule_arn = run_command(
        f"aws elbv2 describe-rules --listener-arn {listener_arn} "
        f"--query \"Rules[?Conditions[?Field=='path-pattern' && contains(Values,'{path}')]].RuleArn\" "
        "--output text"
    ) or ""
    if not rule_arn or rule_arn == "None":
        print(f"[INFO] Creating new ALB rule for {service_name} path '{path}'")
        run_command(
            f"aws elbv2 create-rule --listener-arn {listener_arn} --priority {priority} "
            f"--conditions Field=path-pattern,Values={path} "
            f"--actions Type=forward,TargetGroupArn={target_group_arn}"
        )
    else:
        print(f"[INFO] Updating existing ALB rule for {service_name} path '{path}'")
        run_command(
            f"aws elbv2 modify-rule --rule-arn {rule_arn} "
            f"--conditions Field=path-pattern,Values={path} "
            f"--actions Type=forward,TargetGroupArn={target_group_arn}"
        )

# Deploy ALB rules for a service
def deploy_service(listener_arn, target_group_arn, paths, service_name, starting_priority=10):
    if not target_group_arn:
        print(f"[INFO] Skipping {service_name} ALB rule deployment: Target group ARN not provided.")
        return
    priority = starting_priority
    for path in paths:
        create_or_update_rule(listener_arn, path, target_group_arn, priority, service_name)
        priority += 1

# Swap active/inactive environment after successful deployment
def swap_env(active_env, inactive_env):
    return inactive_env, active_env

# Upload deployment metadata to S3
def save_outputs_to_s3(outputs, aws_access_key, aws_secret_key, aws_region, bucket_name):
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    local_file = "/tmp/deploy_metadata.json"
    s3_file = f"deployments/deploy_metadata_{timestamp}.json"
    with open(local_file, "w") as f:
        json.dump(outputs, f, indent=2)
    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )
    s3.upload_file(local_file, bucket_name, s3_file)
    print(f"Deployment metadata uploaded to s3://{bucket_name}/{s3_file}")
    return local_file

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-json", required=True)
    args = parser.parse_args()

    # Load infra JSON
    with open(args.outputs_json) as f:
        infra = json.load(f)
    listener_arn = infra.get("alb_listener_arn")

    # Environment variables
    pem_path = os.path.expanduser(os.environ["PEM_PATH"])
    aws_access_key = os.environ["AWS_ACCESS_KEY_ID"]
    aws_secret_key = os.environ["AWS_SECRET_ACCESS_KEY"]
    aws_region = os.environ["AWS_REGION"]
    s3_bucket = os.environ["DEPLOY_METADATA_S3_BUCKET"]
    github_actor = os.environ.get("GITHUB_ACTOR", "unknown")

    # Worker
    worker_current = os.environ["WORKER_CURRENT_IMAGE"].split("/")[-1]
    worker_previous = os.environ["WORKER_PREVIOUS_IMAGE"].split("/")[-1]
    worker_status = os.environ["WORKER_STATUS"].lower()
    worker_instance_ids = os.environ.get("WORKER_INSTANCE_IDS", "")

    # Backend
    backend_current = os.environ["BACKEND_CURRENT_IMAGE"].split("/")[-1]
    backend_previous = os.environ["BACKEND_PREVIOUS_IMAGE"].split("/")[-1]
    backend_status = os.environ["BACKEND_STATUS"].lower()
    backend_active_env = os.environ["BACKEND_ACTIVE_ENV"].upper()
    backend_inactive_env = os.environ["BACKEND_INACTIVE_ENV"].upper()
    backend_active_tg = os.environ.get("BACKEND_ACTIVE_TG", "")
    backend_inactive_tg = os.environ.get("BACKEND_INACTIVE_TG", "")
    backend_instance_ids = os.environ.get("BACKEND_INSTANCE_IDS", "")

    # Frontend
    frontend_current = os.environ["FRONTEND_CURRENT_IMAGE"].split("/")[-1]
    frontend_previous = os.environ["FRONTEND_PREVIOUS_IMAGE"].split("/")[-1]
    frontend_status = os.environ["FRONTEND_STATUS"].lower()
    frontend_active_env = os.environ["FRONTEND_ACTIVE_ENV"].upper()
    frontend_inactive_env = os.environ["FRONTEND_INACTIVE_ENV"].upper()
    frontend_active_tg = os.environ.get("FRONTEND_ACTIVE_TG", "")
    frontend_inactive_tg = os.environ.get("FRONTEND_INACTIVE_TG", "")
    frontend_instance_ids = os.environ.get("FRONTEND_INSTANCE_IDS", "")

    deployed_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 1: Deploy Worker
    if worker_status != "skipped":
        deploy_containers(worker_instance_ids, pem_path, "worker", aws_access_key, aws_secret_key, aws_region)
    else:
        print("[INFO] Skipping Worker deployment because WORKER_STATUS is 'skipped'.")

    # Step 2: Deploy Backend ALB rules and swap environments
    if backend_status != "skipped":
        deploy_service(listener_arn, backend_inactive_tg, ["/api/aws/*"], "Backend", starting_priority=10)
        backend_active_env, backend_inactive_env = swap_env(backend_active_env, backend_inactive_env)
        backend_active_tg, backend_inactive_tg = swap_env(backend_active_tg, backend_inactive_tg)
    else:
        print("[INFO] Skipping Backend deployment because BACKEND_STATUS is 'skipped'.")

    # Step 3: Deploy Frontend ALB rules and swap environments
    if frontend_status != "skipped":
        deploy_service(listener_arn, frontend_inactive_tg, ["/", "/favicon.ico", "/robots.txt", "/static/*"], "Frontend", starting_priority=500)
        frontend_active_env, frontend_inactive_env = swap_env(frontend_active_env, frontend_inactive_env)
        frontend_active_tg, frontend_inactive_tg = swap_env(frontend_active_tg, frontend_inactive_tg)
    else:
        print("[INFO] Skipping Frontend deployment because FRONTEND_STATUS is 'skipped'.")

    # Prepare outputs with instance IDs
    outputs = {
        "worker": {
            "current_image": worker_current,
            "previous_image": worker_previous,
            "deployed_at": deployed_at,
            "deployed_by": github_actor,
            "status": worker_status,
            "instance_ids": worker_instance_ids.split(",") if worker_instance_ids else []
            "first_deployment": os.environ.get("WORKER_FIRST_DEPLOYMENT", "false").lower() == "true"
        },
        "backend": {
            "current_image": backend_current,
            "previous_image": backend_previous,
            "active_env": backend_active_env,
            "active_tg": backend_active_tg,
            "inactive_tg": backend_inactive_tg,
            "deployed_at": deployed_at,
            "deployed_by": github_actor,
            "status": backend_status,
            "instance_ids": backend_instance_ids.split(",") if backend_instance_ids else []
            "first_deployment": os.environ.get("BACKEND_FIRST_DEPLOYMENT", "false").lower() == "true"
        },
        "frontend": {
            "current_image": frontend_current,
            "previous_image": frontend_previous,
            "active_env": frontend_active_env,
            "active_tg": frontend_active_tg,
            "inactive_tg": frontend_inactive_tg,
            "deployed_at": deployed_at,
            "deployed_by": github_actor,
            "status": frontend_status,
            "instance_ids": frontend_instance_ids.split(",") if frontend_instance_ids else []
            "first_deployment": os.environ.get("FRONTEND_FIRST_DEPLOYMENT", "false").lower() == "true"
        }
    }


    # Save and print S3 deployment metadata
    local_file = save_outputs_to_s3(outputs, aws_access_key, aws_secret_key, aws_region, s3_bucket)
    print("\n=== Deployment Completed Successfully! ===")
    print("Deployment metadata (uploaded to S3) contains the following values:")
with open(local_file) as f:
    print(f.read())
