#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
def log(msg: str):
    print(f"[frontend-rollback] {msg}", flush=True)

# -------------------------------------------------------------------
# Command helpers
# -------------------------------------------------------------------
def run(cmd: list[str]) -> str:
    log(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        log(f"ERROR: {res.stderr.strip()}")
        raise RuntimeError(f"Command failed: {cmd}")
    return res.stdout.strip()
    
# -------------------------------------------------------------------
# AWS EC2 helper
# -------------------------------------------------------------------
def get_instance_public_ips(instance_ids: list[str]) -> list[str]:
    """
    Fetch public IP addresses for given EC2 instance IDs.
    """
    if not instance_ids:
        return []

    cmd = [
        "aws", "ec2", "describe-instances",
        "--instance-ids", *instance_ids,
        "--query", "Reservations[*].Instances[*].PublicIpAddress",
        "--output", "text"
    ]

    output = run(cmd)  # reuse your existing run() function
    ips = output.split()
    return ips

def ssh_exec(host: str, cmd: str):
    pem = os.getenv("PEM_PATH")
    user = os.getenv("SSH_USER", "ec2-user")
    ssh_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-i", pem,
        f"{user}@{host}", cmd
    ]
    return run(ssh_cmd)

# -------------------------------------------------------------------
# Docker helpers
# -------------------------------------------------------------------
def stop_rm_container(host: str, name: str):
    log(f"[function stop_rm_container] stopping/removing container={name} on host={host}")
    try:
        ssh_exec(host, f"docker rm -f {name} || true")
    except Exception as e:
        log(f"ignore error removing {name} on {host}: {e}")

def run_container(host: str, name: str, image: str):
    log(f"[function run_container] running container={name} image={image} on host={host}")
    try:
        dockerhub_user = os.getenv("DOCKERHUB_USERNAME")
        dockerhub_token = os.getenv("DOCKERHUB_TOKEN")

        # Add DockerHub prefix if missing
        if "/" not in image and dockerhub_user:
            image = f"{dockerhub_user}/{image}"
            log(f"[function run_container] resolved full DockerHub image={image}")

        # Perform DockerHub login
        if dockerhub_user and dockerhub_token:
            ssh_exec(host, f"echo {dockerhub_token} | docker login -u {dockerhub_user} --password-stdin")

        # Pull + run container
        ssh_exec(host, f"docker pull {image} || true")
        ssh_exec(host, f"docker run -d --restart unless-stopped --name {name} {image}")

    except Exception as e:
        log(f"failed to run {name} on {host}: {e}")
        raise


# -------------------------------------------------------------------
# ALB helpers
# -------------------------------------------------------------------
def deregister_targets(tg_arn: str, ids: list[str]):
    if not tg_arn or not ids:
        log("[function deregister_targets] no tg or ids provided → skipping")
        return
    log(f"[function deregister_targets] deregistering targets={ids} from tg={tg_arn}")
    targets = []
    for i in ids:
        targets.extend([f"Id={i}"])
    run(["aws", "elbv2", "deregister-targets", "--target-group-arn", tg_arn, "--targets"] + targets)
    run(["aws", "elbv2", "wait", "target-deregistered", "--target-group-arn", tg_arn, "--targets"] + targets)

def delete_rules(listener_arn: str, tg_arn: str):
    if not listener_arn or not tg_arn:
        log("[function delete_rules] no listener or tg → skipping")
        return
    log(f"[function delete_rules] scanning listener={listener_arn} for tg={tg_arn}")
    rules_json = run(["aws", "elbv2", "describe-rules", "--listener-arn", listener_arn])
    rules = json.loads(rules_json).get("Rules", [])
    for r in rules:
        actions = r.get("Actions", [])
        for a in actions:
            fwd = a.get("ForwardConfig", {})
            for tg in fwd.get("TargetGroups", []):
                if tg.get("TargetGroupArn") == tg_arn:
                    arn = r["RuleArn"]
                    log(f"Deleting listener rule {arn} → TG {tg_arn}")
                    run(["aws", "elbv2", "delete-rule", "--rule-arn", arn])

# -------------------------------------------------------------------
# GitHub output helper
# -------------------------------------------------------------------
def set_output(key: str, val: str):
    log(f"[function set_output] {key}={val}")
    ghout = os.getenv("GITHUB_OUTPUT", "/dev/null")
    with open(ghout, "a") as f:
        f.write(f"{key}={val}\n")
    os.environ[key] = val

# -------------------------------------------------------------------
# Main rollback logic (frontend only)
# -------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--deployment-json", required=True)
    p.add_argument("--infra-json", required=True)
    p.add_argument("--components", required=True, nargs="+", help="list of components in current deployment")
    args = p.parse_args()

    log("[main] loading deployment.json and infra.json")
    with open(args.deployment_json) as f:
        deployment = json.load(f)
    with open(args.infra_json) as f:
        infra = json.load(f)

    frontend = deployment.get("frontend", {})
    frontend_status = frontend.get("status", "")
    first_deploy = frontend.get("first_deployment", False)

    log(f"[main] components={args.components}")
    log(f"[main] frontend_status={frontend_status}, first_deployment={first_deploy}")

    # ------------------ COMPONENT CHECK ------------------
    components = [c.strip().lower() for c in args.components]
    if "all" in components or "frontend" in components:
        log("[main] frontend included in components → proceeding with rollback")
    else:
        log("[main] frontend not in components → exiting with empty outputs")
        set_output("frontend_status", "")
        return


    # ------------------ FRONTEND LOGIC ------------------
    if first_deploy:
        log("[frontend-block] first deployment rollback flow")
        delete_rules(infra.get("alb_listener_arn"), infra.get("frontend_blue_tg_arn"))
        delete_rules(infra.get("alb_listener_arn"), infra.get("frontend_green_tg_arn"))
        deregister_targets(infra.get("frontend_blue_tg_arn"), infra.get("ec2_instance_ids", []))
        deregister_targets(infra.get("frontend_green_tg_arn"), infra.get("ec2_instance_ids", []))
        for ip in infra.get("ec2_instance_ids", []):
            stop_rm_container(ip, "frontend-blue")
            stop_rm_container(ip, "frontend-green")
        set_output("frontend_status", "cleaned")

    elif not first_deploy and frontend_status == "success":
        curr_env = frontend.get("active_env", "")
        inactive_env = "green" if curr_env.lower() == "blue" else "blue"
        prev_image = frontend.get("previous_image", "")
        log(f"[frontend-block] rollback non-first deployment → inactive_env={inactive_env}, prev_image={prev_image}")
    
        instance_ids = infra.get("ec2_instance_ids", [])
        ips = get_instance_public_ips(instance_ids)
    
        log(f"[frontend-block] resolved instance_ids={instance_ids} → public_ips={ips}")
    
        for ip in ips:
            stop_rm_container(ip, f"frontend-{inactive_env}")
            if prev_image:
                run_container(ip, f"frontend-{inactive_env}", prev_image)
    
        set_output("frontend_status", "prepared")


    elif not first_deploy and frontend_status == "skipped":
        log("[frontend-block] frontend skipped → no rollback")
        set_output("frontend_status", "")

    else:
        log("[frontend-block] no matching rollback condition")
        set_output("frontend_status", "")

    log("[main] frontend rollback evaluation completed")

# -------------------------------------------------------------------
if __name__ == "__main__":
    main()
