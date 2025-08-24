import argparse
import json
import boto3
import subprocess
import datetime
import paramiko  # pip install paramiko

def run_command(cmd):
    """Run shell command and return output."""
    print(f"Running command: {cmd}")
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        print(f"Command failed: {cmd}\n{result.stderr}")
        raise RuntimeError(f"Command failed: {cmd}")
    return result.stdout.strip()

def create_or_update_rule(listener_arn, path, target_group_arn, priority):
    """Create or update ALB listener rule for a given path."""
    if not target_group_arn:
        raise ValueError(f"Empty TargetGroupArn for path '{path}' (priority {priority}).")

    print(f"Processing ALB rule: path='{path}' -> TG='{target_group_arn}'")
    try:
        rule_arn = run_command(
            f"aws elbv2 describe-rules --listener-arn {listener_arn} "
            f"--query \"Rules[?Conditions[?Field=='path-pattern' && contains(Values,'{path}')]].RuleArn\" "
            "--output text"
        )
    except RuntimeError:
        rule_arn = ""

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

def deploy_worker_on_instance(instance_ip, pem_path):
    """Deploy worker container on a single instance via SSH."""
    print(f"Deploying worker on instance {instance_ip}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(instance_ip, username="ec2-user", key_filename=pem_path)

    # Remove old worker container if it exists
    remove_cmd = "docker rm -f worker || true"
    stdin, stdout, stderr = ssh.exec_command(remove_cmd)
    out, err = stdout.read().decode(), stderr.read().decode()
    if err:
        print(f"[{instance_ip}] Remove old worker error: {err.strip()}")
    else:
        print(f"[{instance_ip}] Old worker removed (if existed).")

    # Rename worker_new -> worker
    rename_cmd = "docker rename worker_new worker || true"
    stdin, stdout, stderr = ssh.exec_command(rename_cmd)
    out, err = stdout.read().decode(), stderr.read().decode()
    if err:
        print(f"[{instance_ip}] Rename worker_new error: {err.strip()}")
    else:
        print(f"[{instance_ip}] worker_new renamed to worker.")

    ssh.close()
    print(f"[{instance_ip}] Worker deployment completed.")

def deploy_worker(instance_ids, pem_path, aws_access_key, aws_secret_key, aws_region):
    """Deploy worker container across multiple EC2 instances."""
    ec2 = boto3.client(
        "ec2",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )

    # Resolve instance IDs to public IPs
    reservations = ec2.describe_instances(InstanceIds=instance_ids.split(","))["Reservations"]
    for res in reservations:
        for inst in res["Instances"]:
            public_ip = inst.get("PublicIpAddress")
            if public_ip:
                deploy_worker_on_instance(public_ip, pem_path)
            else:
                print(f"Instance {inst['InstanceId']} does not have a public IP, skipping worker deployment.")

def deploy_service(listener_arn, target_group_arn, paths, starting_priority=10):
    """Deploy backend/frontend ALB rules."""
    priority = starting_priority
    for path in paths:
        create_or_update_rule(listener_arn, path, target_group_arn, priority)
        priority += 1

def save_outputs_to_s3(outputs, aws_access_key, aws_secret_key, aws_region, bucket_name):
    """Save deployment metadata JSON to S3 with timestamped filename."""
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    local_file = "/tmp/deploy_metadata.json"
    s3_file = f"deployments/deploy_metadata_{timestamp}.json"

    with open(local_file, "w") as f:
        json.dump(outputs, f, indent=2)

    print(f"Uploading deployment metadata to S3 bucket: {bucket_name}")
    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )
    s3.upload_file(local_file, bucket_name, s3_file)
    print(f"Deployment metadata uploaded to s3://{bucket_name}/{s3_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy Metadata Script")
    parser.add_argument("--pem-path", required=True)
    parser.add_argument("--worker-status", required=True)
    parser.add_argument("--instance-ids", required=True)
    parser.add_argument("--backend-current-image", required=True)
    parser.add_argument("--backend-previous-image", required=True)
    parser.add_argument("--frontend-current-image", required=True)
    parser.add_argument("--frontend-previous-image", required=True)
    parser.add_argument("--backend-blue-tg", required=True)
    parser.add_argument("--backend-green-tg", required=True)
    parser.add_argument("--backend-active-env", required=True)
    parser.add_argument("--frontend-blue-tg", required=True)
    parser.add_argument("--frontend-green-tg", required=True)
    parser.add_argument("--frontend-active-env", required=True)
    parser.add_argument("--infra-outputs-json", required=True)
    parser.add_argument("--dockerhub-username", required=True)
    parser.add_argument("--dockerhub-token", required=True)
    parser.add_argument("--aws-access-key-id", required=True)
    parser.add_argument("--aws-secret-access-key", required=True)
    parser.add_argument("--aws-region", required=True)
    parser.add_argument("--image-repo", required=True)
    parser.add_argument("--listener-arn", required=True)
    parser.add_argument("--s3-bucket", required=True)
    parser.add_argument("--github-actor", required=True)
    args = parser.parse_args()

    print("Starting deployment process...")
    deployed_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Worker deployment across instances
    deploy_worker(args.instance_ids, args.pem_path, args.aws_access_key_id, args.aws_secret_access_key, args.aws_region)

    # Normalize env names to uppercase
    backend_env = args.backend_active_env.strip().upper()
    frontend_env = args.frontend_active_env.strip().upper()

    # Backend deployment
    backend_tg = args.backend_green_tg if backend_env == "BLUE" else args.backend_blue_tg
    backend_paths = ["/api/aws/*"]
    deploy_service(args.listener_arn, backend_tg, backend_paths, starting_priority=10)

    # Frontend deployment
    frontend_tg = args.frontend_green_tg if frontend_env == "BLUE" else args.frontend_blue_tg
    frontend_paths = ["/", "/favicon.ico", "/robots.txt", "/static/*"]
    deploy_service(args.listener_arn, frontend_tg, frontend_paths, starting_priority=500)

    # Prepare deployment outputs
    outputs = {
        "worker": {
            "deployed_at": deployed_at,
            "deployed_by": args.github_actor,
            "status": args.worker_status
        },
        "backend": {
            "current_image": args.backend_current_image,
            "previous_image": args.backend_previous_image,
            "active_env": backend_env,
            "blue_tg": args.backend_blue_tg,
            "green_tg": args.backend_green_tg,
            "deployed_at": deployed_at,
            "deployed_by": args.github_actor,
            "status": "success"
        },
        "frontend": {
            "current_image": args.frontend_current_image,
            "previous_image": args.frontend_previous_image,
            "active_env": frontend_env,
            "blue_tg": args.frontend_blue_tg,
            "green_tg": args.frontend_green_tg,
            "deployed_at": deployed_at,
            "deployed_by": args.github_actor,
            "status": "success"
        }
    }

    # Upload deployment metadata to S3
    save_outputs_to_s3(outputs, args.aws_access_key_id, args.aws_secret_access_key, args.aws_region, args.s3_bucket)

    # GitHub Actions outputs
    for svc in ["worker", "backend", "frontend"]:
        for key, value in outputs[svc].items():
            print(f"::set-output name={svc}_{key}::{value}")

    print("Deployment process completed successfully!")
    print(json.dumps(outputs, indent=2))
