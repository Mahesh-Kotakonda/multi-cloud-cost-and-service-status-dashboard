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

    # Remove old container
    remove_cmd = f"docker rm -f {container_name} || true"
    stdin, stdout, stderr = ssh.exec_command(remove_cmd)
    out, err = stdout.read().decode(), stderr.read().decode()
    if err.strip():
        print(f"[{instance_ip}] Remove old {container_name} error: {err.strip()}")
    else:
        print(f"[{instance_ip}] Old {container_name} removed (if existed).")

    # Rename new container
    rename_cmd = f"docker rename {container_name}_new {container_name} || true"
    stdin, stdout, stderr = ssh.exec_command(rename_cmd)
    out, err = stdout.read().decode(), stderr.read().decode()
    if err.strip():
        print(f"[{instance_ip}] Rename {container_name}_new error: {err.strip()}")
    else:
        print(f"[{instance_ip}] {container_name}_new renamed to {container_name}.")

    ssh.close()
    print(f"[{instance_ip}] {container_name} deployment completed.")

# Deploy across multiple instances
def deploy_containers(instance_ids, pem_path, container_name, aws_access_key, aws_secret_key, aws_region):
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
                print(f"Instance {inst['InstanceId']} has no public IP, skipping {container_name} deployment.")

# ALB rule management
def create_or_update_rule(listener_arn, path, target_group_arn, priority):
    if not target_group_arn:
        print(f"Skipping ALB rule for path '{path}', target group ARN not found.")
        return
    print(f"Processing ALB rule: path='{path}' -> TG='{target_group_arn}'")
    rule_arn = run_command(
        f"aws elbv2 describe-rules --listener-arn {listener_arn} "
        f"--query \"Rules[?Conditions[?Field=='path-pattern' && contains(Values,'{path}')]].RuleArn\" "
        "--output text"
    ) or ""
    if not rule_arn or rule_arn == "None":
        print(f"Creating new rule for {path}")
        run_command(
            f"aws elbv2 create-rule --listener-arn {listener_arn} --priority {priority} "
            f"--conditions Field=path-pattern,Values={path} "
            f"--actions Type=forward,TargetGroupArn={target_group_arn}"
        )
    else:
        print(f"Updating existing rule for {path}")
        run_command(
            f"aws elbv2 modify-rule --rule-arn {rule_arn} "
            f"--conditions Field=path-pattern,Values={path} "
            f"--actions Type=forward,TargetGroupArn={target_group_arn}"
        )

# Deploy ALB rules
def deploy_service(listener_arn, target_group_arn, paths, starting_priority=10):
    priority = starting_priority
    for path in paths:
        create_or_update_rule(listener_arn, path, target_group_arn, priority)
        priority += 1

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

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-json", required=True)
    args = parser.parse_args()

    # Load infra JSON (only for listener ARN)
    with open(args.outputs_json) as f:
        infra = json.load(f)
    listener_arn = infra.get("alb_listener_arn")

    # Environment variables
    pem_path = os.environ["PEM_PATH"]
    aws_access_key = os.environ["AWS_ACCESS_KEY_ID"]
    aws_secret_key = os.environ["AWS_SECRET_ACCESS_KEY"]
    aws_region = os.environ["AWS_REGION"]
    s3_bucket = os.environ["DEPLOY_METADATA_S3_BUCKET"]
    github_actor = os.environ.get("GITHUB_ACTOR", "unknown")

    # Worker
    worker_current = os.environ["WORKER_CURRENT_IMAGE"]
    worker_previous = os.environ["WORKER_PREVIOUS_IMAGE"]
    worker_status = os.environ["WORKER_STATUS"]
    worker_instance_ids = os.environ["WORKER_INSTANCE_IDS"]

    # Backend
    backend_current = os.environ["BACKEND_CURRENT_IMAGE"]
    backend_previous = os.environ["BACKEND_PREVIOUS_IMAGE"]
    backend_status = os.environ["BACKEND_STATUS"]
    backend_active_env = os.environ["BACKEND_ACTIVE_ENV"].upper()
    backend_inactive_env = os.environ["BACKEND_INACTIVE_ENV"].upper()
    backend_active_tg = os.environ["BACKEND_ACTIVE_TG"]
    backend_inactive_tg = os.environ["BACKEND_INACTIVE_TG"]
    backend_instance_ids = os.environ["BACKEND_INSTANCE_IDS"]

    # Frontend
    frontend_current = os.environ["FRONTEND_CURRENT_IMAGE"]
    frontend_previous = os.environ["FRONTEND_PREVIOUS_IMAGE"]
    frontend_status = os.environ["FRONTEND_STATUS"]
    frontend_active_env = os.environ["FRONTEND_ACTIVE_ENV"].upper()
    frontend_inactive_env = os.environ["FRONTEND_INACTIVE_ENV"].upper()
    frontend_active_tg = os.environ["FRONTEND_ACTIVE_TG"]
    frontend_inactive_tg = os.environ["FRONTEND_INACTIVE_TG"]
    frontend_instance_ids = os.environ["FRONTEND_INSTANCE_IDS"]

    deployed_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 1: Deploy Worker
    deploy_containers(worker_instance_ids, pem_path, "worker", aws_access_key, aws_secret_key, aws_region)

    # Step 2: Deploy Backend ALB rules
    backend_tg = backend_inactive_tg if backend_active_env == "BLUE" else backend_active_tg
    deploy_service(listener_arn, backend_tg, ["/api/aws/*"], starting_priority=10)
    deploy_containers(backend_instance_ids, pem_path, "backend", aws_access_key, aws_secret_key, aws_region)

    # Step 3: Deploy Frontend ALB rules
    frontend_tg = frontend_inactive_tg if frontend_active_env == "BLUE" else frontend_active_tg
    deploy_service(listener_arn, frontend_tg, ["/", "/favicon.ico", "/robots.txt", "/static/*"], starting_priority=500)
    deploy_containers(frontend_instance_ids, pem_path, "frontend", aws_access_key, aws_secret_key, aws_region)

    # Prepare outputs
    outputs = {
        "worker": {
            "current_image": worker_current,
            "previous_image": worker_previous,
            "deployed_at": deployed_at,
            "deployed_by": github_actor,
            "status": worker_status
        },
        "backend": {
            "current_image": backend_current,
            "previous_image": backend_previous,
            "active_env": backend_active_env,
            "blue_tg": backend_active_tg,
            "green_tg": backend_inactive_tg,
            "deployed_at": deployed_at,
            "deployed_by": github_actor,
            "status": backend_status
        },
        "frontend": {
            "current_image": frontend_current,
            "previous_image": frontend_previous,
            "active_env": frontend_active_env,
            "blue_tg": frontend_active_tg,
            "green_tg": frontend_inactive_tg,
            "deployed_at": deployed_at,
            "deployed_by": github_actor,
            "status": frontend_status
        }
    }

    save_outputs_to_s3(outputs, aws_access_key, aws_secret_key, aws_region, s3_bucket)

    # Set GitHub outputs
    for svc in ["worker", "backend", "frontend"]:
        for key, value in outputs[svc].items():
            print(f"::set-output name={svc}_{key}::{value}")

    print("Deployment process completed successfully!")
    print(json.dumps(outputs, indent=2))
