#!/usr/bin/env python3

import argparse
import json
import boto3
import subprocess
import datetime
import os
from pathlib import Path

def run_command(cmd):
    """Run shell command and capture output."""
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result.stdout.strip()

def create_or_update_rule(listener_arn, path, target_group_arn, priority):
    """Create or update ALB listener rule for a given path."""
    try:
        rule_arn = run_command(
            f"aws elbv2 describe-rules --listener-arn {listener_arn} "
            f"--query \"Rules[?Conditions[?Field=='path-pattern' && contains(Values,'{path}')]].RuleArn\" "
            "--output text"
        )
    except RuntimeError:
        rule_arn = ""

    if not rule_arn or rule_arn == "None":
        print(f"Creating rule {path} -> TG {target_group_arn}")
        run_command(
            f"aws elbv2 create-rule --listener-arn {listener_arn} --priority {priority} "
            f"--conditions Field=path-pattern,Values={path} "
            f"--actions Type=forward,TargetGroupArn={target_group_arn}"
        )
    else:
        print(f"Updating rule {path} -> TG {target_group_arn}")
        run_command(
            f"aws elbv2 modify-rule --rule-arn {rule_arn} "
            f"--conditions Field=path-pattern,Values={path} "
            f"--actions Type=forward,TargetGroupArn={target_group_arn}"
        )

def deploy_worker(current_image, previous_image, pem_path):
    """Simulate worker deployment logic."""
    # Assuming Docker is used to run the container
    print(f"Deploying worker container {current_image}...")
    # Remove previous container if exists
    try:
        run_command("docker rm -f worker || true")
    except RuntimeError:
        pass
    # Rename new container to 'worker'
    run_command(f"docker rename worker_new worker || true")
    print("Worker deployment completed.")

def deploy_backend(frontend=False):
    """Deploy backend or frontend ALB rules."""
    rules = [
        ("/api/aws/*", args.backend_tg)
    ] if not frontend else [
        ("/", args.frontend_tg),
        ("/favicon.ico", args.frontend_tg),
        ("/robots.txt", args.frontend_tg),
        ("/static/*", args.frontend_tg)
    ]

    priority = 10 if not frontend else 500
    for path, tg in rules:
        create_or_update_rule(args.listener_arn, path, tg, priority)
        priority += 1

def save_outputs_to_s3(outputs, bucket_name, prefix="deployments"):
    """Save deployment outputs JSON to S3 with timestamp."""
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{prefix}/deploy_metadata_{timestamp}.json"
    with open("/tmp/deploy_metadata.json", "w") as f:
        json.dump(outputs, f, indent=2)

    s3 = boto3.client(
        "s3",
        aws_access_key_id=args.aws_access_key_id,
        aws_secret_access_key=args.aws_secret_access_key,
        region_name=args.aws_region
    )
    s3.upload_file("/tmp/deploy_metadata.json", bucket_name, filename)
    print(f"Deployment metadata uploaded to s3://{bucket_name}/{filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy Metadata Script")
    parser.add_argument("--pem-path", required=True)
    parser.add_argument("--worker-current-image", required=True)
    parser.add_argument("--worker-previous-image", required=True)
    parser.add_argument("--worker-status", required=True)
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
    args = parser.parse_args()

    # Deploy worker container
    deploy_worker(args.worker_current_image, args.worker_previous_image, args.pem_path)

    # Deploy backend rules
    backend_tg = args.backend_green_tg if args.backend_active_env == "blue" else args.backend_blue_tg
    args.backend_tg = backend_tg
    deploy_backend(frontend=False)

    # Deploy frontend rules
    frontend_tg = args.frontend_green_tg if args.frontend_active_env == "blue" else args.frontend_blue_tg
    args.frontend_tg = frontend_tg
    deploy_backend(frontend=True)

    # Prepare outputs
    deployed_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    outputs = {
        "worker": {
            "current_image": args.worker_current_image,
            "previous_image": args.worker_previous_image,
            "deployed_at": deployed_at,
            "status": "success"
        },
        "backend": {
            "active_env": args.backend_active_env,
            "blue_tg": args.backend_blue_tg,
            "green_tg": args.backend_green_tg,
            "deployed_at": deployed_at,
            "status": "success"
        },
        "frontend": {
            "active_env": args.frontend_active_env,
            "blue_tg": args.frontend_blue_tg,
            "green_tg": args.frontend_green_tg,
            "deployed_at": deployed_at,
            "status": "success"
        }
    }

    # Save outputs to S3
    save_outputs_to_s3(outputs, args.s3_bucket)

    print(json.dumps(outputs, indent=2))
