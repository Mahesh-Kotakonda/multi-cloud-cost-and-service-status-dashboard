#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time

def run_cmd(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def deploy_worker(args, deployment):
    cur_img = deployment["worker"]["current_image"]
    prev_img = deployment["worker"]["previous_image"]
    if cur_img == prev_img:
        print("Worker: first deployment or no change. Skipping rollback.")
        return
    print(f"Rolling back worker: {cur_img} -> {prev_img}")
    # SSH to instances, deploy worker_rollback, health check, remove old container, rename
    # Implementation same as your app deploy logic

def deploy_backend(args, deployment):
    active_env = deployment["backend"]["active_env"]
    inactive_env = "BLUE" if active_env == "GREEN" else "GREEN"
    prev_img = deployment["backend"]["previous_image"]
    print(f"Rolling back backend: deploying previous image {prev_img} to {inactive_env}")
    # Deploy previous image if not present, health check

def deploy_frontend(args, deployment):
    active_env = deployment["frontend"]["active_env"]
    inactive_env = "BLUE" if active_env == "GREEN" else "GREEN"
    prev_img = deployment["frontend"]["previous_image"]
    print(f"Rolling back frontend: deploying previous image {prev_img} to {inactive_env}")
    # Deploy previous image if not present, health check

def metadata_job(args, deployment):
    print("Metadata job: rename worker and switch target groups for backend/frontend")
    # SSH rename worker, update ALB listeners

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=["worker","backend","frontend","metadata"])
    parser.add_argument("--deployment-json-path", required=True)
    parser.add_argument("--aws-access-key-id", required=True)
    parser.add_argument("--aws-secret-access-key", required=True)
    parser.add_argument("--aws-region", required=True)
    parser.add_argument("--docker-username", required=True)
    parser.add_argument("--docker-password", required=True)
    parser.add_argument("--image-repo", required=True)
    parser.add_argument("--db-host")
    parser.add_argument("--db-port")
    parser.add_argument("--db-user")
    parser.add_argument("--db-pass")
    parser.add_argument("--s3-bucket", required=True)
    parser.add_argument("--pem-path", required=True)
    parser.add_argument("--reason")
    args = parser.parse_args()

    with open(args.deployment_json_path) as f:
        deployment = json.load(f)

    if args.component == "worker":
        deploy_worker(args, deployment)
    elif args.component == "backend":
        deploy_backend(args, deployment)
    elif args.component == "frontend":
        deploy_frontend(args, deployment)
    elif args.component == "metadata":
        metadata_job(args, deployment)

if __name__ == "__main__":
    main()
