import argparse
import json
import boto3
import subprocess
import datetime

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

def deploy_worker(current_image, previous_image):
    """Deploy worker container: remove old and rename new."""
    print(f"Deploying worker container: {current_image}")
    try:
        run_command("docker rm -f worker || true")
    except RuntimeError:
        print("No existing worker container to remove.")
    run_command("docker rename worker_new worker || true")
    print("Worker deployment completed.")

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
    parser.add_argument("--worker-current-image", required=True)
    parser.add_argument("--worker-previous-image", required=True)
    parser.add_argument("--worker-status", required=True)
    parser.add_argument("--backend-current-image", required=True)
    parser.add_argument("--backend-previous-image", required=True)
    parser.add_argument("--frontend-current-image", required=True)
    parser.add_argument("--frontend-previous-image", required=True)
    parser.add_argument("--instance-ids", required=True)
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

    # Worker deployment
    deploy_worker(args.worker_current_image, args.worker_previous_image)

    # Normalize env names to uppercase
    backend_env = args.backend_active_env.strip().upper()
    frontend_env = args.frontend_active_env.strip().upper()

    # Backend deployment (switch TG based on active env)
    backend_tg = args.backend_green_tg if backend_env == "BLUE" else args.backend_blue_tg
    if not backend_tg:
        raise ValueError("Resolved backend target group ARN is empty. Check --backend-* arguments and backend_active_env.")
    backend_paths = ["/api/aws/*"]
    print(f"Deploying backend with active environment: {backend_env}")
    deploy_service(args.listener_arn, backend_tg, backend_paths, starting_priority=10)

    # Frontend deployment (switch TG based on active env)
    frontend_tg = args.frontend_green_tg if frontend_env == "BLUE" else args.frontend_blue_tg
    if not frontend_tg:
        raise ValueError("Resolved frontend target group ARN is empty. Check --frontend-* arguments and frontend_active_env.")
    frontend_paths = ["/", "/favicon.ico", "/robots.txt", "/static/*"]
    print(f"Deploying frontend with active environment: {frontend_env}")
    deploy_service(args.listener_arn, frontend_tg, frontend_paths, starting_priority=500)

    # Prepare deployment outputs
    outputs = {
        "worker": {
            "current_image": args.worker_current_image,
            "previous_image": args.worker_previous_image,
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

    # Upload to S3
    save_outputs_to_s3(outputs, args.aws_access_key_id, args.aws_secret_access_key, args.aws_region, args.s3_bucket)

    # GitHub Actions outputs
    for svc in ["worker", "backend", "frontend"]:
        for key, value in outputs[svc].items():
            print(f"::set-output name={svc}_{key}::{value}")

    print("Deployment process completed successfully!")
    print(json.dumps(outputs, indent=2))
