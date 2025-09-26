#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
def log(msg: str):
    print(f"[worker-rollback] {msg}", flush=True)


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
# AWS helpers
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

    # prepend user if missing
    if "/" not in image and dockerhub_user:
        image = f"{dockerhub_user}/{image}"

    if dockerhub_user and dockerhub_token:
        ssh_exec(host, f"echo {dockerhub_token} | docker login -u {dockerhub_user} --password-stdin")

    ssh_exec(host, f"docker pull {image} || true")
    ssh_exec(host, f"docker run -d --restart unless-stopped --name {name} {image}")


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

    worker = deployment.get("worker", {})
    worker_status = worker.get("status", "")
    first_deploy = worker.get("first_deployment", False)

    components = [c.strip().lower() for c in args.components]
    if not ("all" in components or "worker" in components):
        log("worker not in components → skipping rollback")
        set_output("worker_status", "")
        return

    instance_ids = worker.get("instance_ids") or infra.get("ec2_instance_ids", [])
    ips = get_instance_public_ips(instance_ids)

    # ------------------ FIRST DEPLOYMENT ROLLBACK ------------------
    if first_deploy:
        log("First deployment rollback → just cleanup worker containers")
        for ip in ips:
            stop_rm_container(ip, "worker")
            stop_rm_container(ip, "worker_new")

        set_output("worker_status", "cleaned")
        set_output("worker_current_image", "")
        set_output("worker_previous_image", "")
        set_output("worker_first_deployment", "true")
        set_output("worker_instance_ids", ",".join(instance_ids))

    # ------------------ NON-FIRST DEPLOYMENT ROLLBACK ------------------
    elif worker_status == "success":
        prev_image = worker.get("previous_image", "")
        curr_image = worker.get("current_image", "")

        log(f"Rollback worker → prev={prev_image}, curr={curr_image}")

        for ip in ips:
            stop_rm_container(ip, "worker_new")
            if prev_image:
                run_container(ip, "worker_new", prev_image)

        set_output("worker_status", "restored")
        set_output("worker_current_image", curr_image)
        set_output("worker_previous_image", prev_image)
        set_output("worker_first_deployment", "false")
        set_output("worker_instance_ids", ",".join(instance_ids))

    # ------------------ SKIPPED / NO MATCH ------------------
    else:
        log("worker rollback skipped → unknown state")
        set_output("worker_status", "")
        set_output("worker_current_image", "")
        set_output("worker_previous_image", "")
        set_output("worker_first_deployment", "false")
        set_output("worker_instance_ids", ",".join(instance_ids))


if __name__ == "__main__":
    main()
