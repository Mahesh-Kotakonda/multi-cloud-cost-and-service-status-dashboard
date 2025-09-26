#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
def log(msg: str):
    print(f"[backend-rollback] {msg}", flush=True)


def run(cmd: list[str]) -> str:
    log(f"[run] START → Executing: {' '.join(cmd)}")
    start = time.time()

    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = round(time.time() - start, 2)

    if res.returncode != 0:
        log(f"[run] ERROR → Command failed after {elapsed}s: {' '.join(cmd)}")
        log(f"[run] STDERR: {res.stderr.strip()}")
        raise RuntimeError(f"Command failed: {cmd}")

    log(f"[run] SUCCESS → Completed in {elapsed}s")
    if res.stdout.strip():
        log(f"[run] STDOUT: {res.stdout.strip()}")

    return res.stdout.strip()


# -------------------------------------------------------------------
# AWS EC2 helper
# -------------------------------------------------------------------
def get_instance_public_ips(instance_ids: list[str]) -> list[str]:
    if not instance_ids:
        return []
    cmd = [
        "aws", "ec2", "describe-instances",
        "--instance-ids", *instance_ids,
        "--query", "Reservations[*].Instances[*].PublicIpAddress",
        "--output", "text"
    ]
    output = run(cmd)
    return output.split()


def ssh_exec(host: str, cmd: str):
    pem = os.getenv("PEM_PATH")
    user = os.getenv("SSH_USER", "ec2-user")
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-i", pem,
        f"{user}@{host}",
        cmd,
    ]
    log(f"[ssh_exec] START → host={host}, cmd={cmd}")
    out = run(ssh_cmd)
    log(f"[ssh_exec] END → host={host}")
    return out


def stop_rm_container(host: str, name: str):
    log(f"[stop_rm_container] removing container={name} on {host}")
    try:
        ssh_exec(host, f"docker rm -f {name} || true")
    except Exception as e:
        log(f"[stop_rm_container] WARNING → ignore error: {e}")


def run_container(host: str, name: str, image: str):
    log(f"[run_container] running container={name}, image={image}, host={host}")
    dockerhub_user = os.getenv("DOCKERHUB_USERNAME")
    dockerhub_token = os.getenv("DOCKERHUB_TOKEN")

    if "/" not in image and dockerhub_user:
        image = f"{dockerhub_user}/{image}"

    if dockerhub_user and dockerhub_token:
        ssh_exec(host, f"echo {dockerhub_token} | docker login -u {dockerhub_user} --password-stdin")

    ssh_exec(host, f"docker pull {image} || true")
    ssh_exec(host, f"docker run -d --restart unless-stopped --name {name} {image}")


# -------------------------------------------------------------------
# ALB helpers
# -------------------------------------------------------------------
def deregister_targets(tg_arn: str, ids: list[str]):
    if not tg_arn or not ids:
        return
    targets = [f"Id={i}" for i in ids]
    run(["aws", "elbv2", "deregister-targets", "--target-group-arn", tg_arn, "--targets"] + targets)
    run(["aws", "elbv2", "wait", "target-deregistered", "--target-group-arn", tg_arn, "--targets"] + targets)


def delete_rules(listener_arn: str, tg_arn: str):
    if not listener_arn or not tg_arn:
        return
    rules_json = run(["aws", "elbv2", "describe-rules", "--listener-arn", listener_arn])
    rules = json.loads(rules_json).get("Rules", [])
    for r in rules:
        for a in r.get("Actions", []):
            for tg in a.get("ForwardConfig", {}).get("TargetGroups", []):
                if tg.get("TargetGroupArn") == tg_arn:
                    arn = r["RuleArn"]
                    run(["aws", "elbv2", "delete-rule", "--rule-arn", arn])


# -------------------------------------------------------------------
# GitHub output helper
# -------------------------------------------------------------------
def set_output(key: str, val: str):
    log(f"[set_output] {key}={val}")
    ghout = os.getenv("GITHUB_OUTPUT", "/dev/null")
    with open(ghout, "a") as f:
        f.write(f"{key}={val}\n")
    os.environ[key] = val


# -------------------------------------------------------------------
# Main rollback logic
# -------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--deployment-json", required=True)
    p.add_argument("--infra-json", required=True)
    p.add_argument("--components", required=True, nargs="+")
    args = p.parse_args()

    with open(args.deployment_json) as f:
        deployment = json.load(f)
    with open(args.infra_json) as f:
        infra = json.load(f)

    backend = deployment.get("backend", {})
    backend_status = backend.get("status", "")
    first_deploy = backend.get("first_deployment", False)

    components = [c.strip().lower() for c in args.components]
    if not ("all" in components or "backend" in components):
        log("backend not in components → skipping rollback")
        set_output("backend_status", "")
        return

    # ------------------ FIRST DEPLOYMENT ROLLBACK ------------------
    if first_deploy:
        delete_rules(infra.get("alb_listener_arn"), infra.get("backend_blue_tg_arn"))
        delete_rules(infra.get("alb_listener_arn"), infra.get("backend_green_tg_arn"))
        deregister_targets(infra.get("backend_blue_tg_arn"), infra.get("ec2_instance_ids", []))
        deregister_targets(infra.get("backend_green_tg_arn"), infra.get("ec2_instance_ids", []))
        for ip in infra.get("ec2_instance_ids", []):
            stop_rm_container(ip, "backend_blue")
            stop_rm_container(ip, "backend_green")

        set_output("backend_status", "cleaned")
        set_output("backend_active_env", "")
        set_output("backend_inactive_env", "")
        set_output("backend_active_tg", "")
        set_output("backend_inactive_tg", "")
        set_output("backend_current_image", "")
        set_output("backend_previous_image", "")
        set_output("backend_first_deployment", "true")
        set_output("backend_instance_ids", ",".join(infra.get("ec2_instance_ids", [])))

    # ------------------ NON-FIRST DEPLOYMENT ROLLBACK ------------------
    elif backend_status == "success":
        curr_env = backend.get("active_env", "")
        inactive_env = "green" if curr_env.lower() == "blue" else "blue"
        prev_image = backend.get("previous_image", "")
        curr_image = backend.get("current_image", "")

        instance_ids = infra.get("ec2_instance_ids", [])
        ips = get_instance_public_ips(instance_ids)

        for ip in ips:
            stop_rm_container(ip, f"backend_{inactive_env}")
            if prev_image:
                run_container(ip, f"backend_{inactive_env}", prev_image)

        set_output("backend_status", "prepared")
        set_output("backend_active_env", curr_env)
        set_output("backend_inactive_env", inactive_env)
        set_output("backend_active_tg",
                   infra.get("backend_blue_tg_arn") if curr_env.lower() == "blue" else infra.get("backend_green_tg_arn"))
        set_output("backend_inactive_tg",
                   infra.get("backend_green_tg_arn") if curr_env.lower() == "blue" else infra.get("backend_blue_tg_arn"))
        set_output("backend_current_image", curr_image)
        set_output("backend_previous_image", prev_image)
        set_output("backend_first_deployment", "false")
        set_output("backend_instance_ids", ",".join(instance_ids))

    # ------------------ SKIPPED / NO MATCH ------------------
    else:
        set_output("backend_status", "")
        set_output("backend_active_env", "")
        set_output("backend_inactive_env", "")
        set_output("backend_active_tg", "")
        set_output("backend_inactive_tg", "")
        set_output("backend_current_image", "")
        set_output("backend_previous_image", "")
        set_output("backend_first_deployment", "false")
        set_output("backend_instance_ids", ",".join(infra.get("ec2_instance_ids", [])))


if __name__ == "__main__":
    main()
