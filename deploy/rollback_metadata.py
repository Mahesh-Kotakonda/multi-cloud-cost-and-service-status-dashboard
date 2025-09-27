#!/usr/bin/env python3
"""
Simple rollback metadata job:
- Worker: rename worker_new -> worker on instances (SSH using PEM_PATH)
- Backend/Frontend: create-or-update ALB rules (same logic as deploy) pointing to INACTIVE TG,
  then register instance IDs into that TG on the expected port.
- No delete/deregister operations (per request).
- Basic wait + describe-target-health logging after registration.
"""

import os
import json
import boto3
import subprocess
import datetime
import paramiko
import time
import sys

# Ports mapping (consistent with your deploy scripts)
FRONTEND_BLUE_PORT = "3000"
FRONTEND_GREEN_PORT = "3001"
BACKEND_BLUE_PORT = "8080"
BACKEND_GREEN_PORT = "8081"

# -------------------------
# Helper: run shell command
# -------------------------
def run_command(cmd):
    print(f"[run_command] {cmd}")
    res = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if res.returncode != 0:
        print(f"[run_command] ERROR: {res.stderr.strip()}")
        raise RuntimeError(f"Command failed: {cmd}")
    out = res.stdout.strip()
    if out:
        print(f"[run_command] STDOUT: {out}")
    return out

# -------------------------
# ALB create/update rule (same as deploy)
# -------------------------
def create_or_update_rule(listener_arn, path, target_group_arn, priority, service_name):
    if not target_group_arn:
        print(f"[INFO] Skipping ALB rule creation for {service_name} path '{path}': Target group ARN not found.")
        return
    print(f"[INFO] Processing ALB rule for {service_name}: path='{path}' -> TG='{target_group_arn}'")
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
        print(f"[INFO] Updating existing ALB rule for {service_name} path '{path}' (rule={rule_arn})")
        run_command(
            f"aws elbv2 modify-rule --rule-arn {rule_arn} "
            f"--conditions Field=path-pattern,Values={path} "
            f"--actions Type=forward,TargetGroupArn={target_group_arn}"
        )

# -------------------------
# Worker: SSH rename worker_new -> worker
# -------------------------
def _get_public_ips(instance_ids, aws_access_key, aws_secret_key, aws_region):
    """Return mapping instance_id -> public_ip for provided instance_ids"""
    if not instance_ids:
        return {}
    ec2 = boto3.client(
        "ec2",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )
    resp = ec2.describe_instances(InstanceIds=instance_ids)
    mapping = {}
    for r in resp.get("Reservations", []):
        for i in r.get("Instances", []):
            iid = i.get("InstanceId")
            mapping[iid] = i.get("PublicIpAddress")  # may be None
    return mapping

def rename_worker_on_instance(public_ip, pem_path):
    print(f"[worker] Connecting to {public_ip} to finalize worker rollback")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(public_ip, username="ec2-user", key_filename=pem_path, timeout=10)

    # remove old worker and rename worker_new -> worker
    cmds = [
        "docker rm -f worker || true",
        "docker rename worker_new worker || true"
    ]
    for c in cmds:
        stdin, stdout, stderr = ssh.exec_command(c)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if out:
            print(f"[{public_ip}] STDOUT: {out}")
        if err:
            print(f"[{public_ip}] STDERR: {err}")
    ssh.close()
    print(f"[worker] Completed on {public_ip}")

def rollback_worker(instance_ids, pem_path, aws_access_key, aws_secret_key, aws_region):
    if not instance_ids:
        print("[worker] No instance ids provided; skipping worker rollback.")
        return
    if not pem_path:
        print("[worker] PEM_PATH not set; skipping worker rollback.")
        return
    ids = [i for i in instance_ids.split(",") if i]
    if not ids:
        print("[worker] No valid instance ids; skipping worker rollback.")
        return
    mapping = _get_public_ips(ids, aws_access_key, aws_secret_key, aws_region)
    for iid in ids:
        public_ip = mapping.get(iid)
        if public_ip:
            try:
                rename_worker_on_instance(public_ip, pem_path)
            except Exception as e:
                print(f"[worker] ERROR handling {iid}@{public_ip}: {e}")
        else:
            print(f"[worker] Instance {iid} has no public IP; skipping.")

# -------------------------
# Register targets into TG (simple)
# -------------------------
def register_targets_to_tg(tg_arn, instance_ids, port):
    """Register the given instance IDs to TG using instance-id registration (simple)."""
    if not tg_arn:
        print("[register_targets] No TG ARN provided, skipping.")
        return
    ids = [i for i in (instance_ids.split(",") if instance_ids else []) if i]
    if not ids:
        print("[register_targets] No instance ids provided, skipping.")
        return
    # Build targets string: Id=i-...,Port=PORT Id=i-...,Port=PORT ...
    targets = " ".join([f"Id={i},Port={port}" for i in ids])
    cmd = f"aws elbv2 register-targets --target-group-arn {tg_arn} --targets {targets}"
    print(f"[register_targets] Running: {cmd}")
    run_command(cmd)
    # Short wait then describe-target-health once for visibility
    time.sleep(2)
    try:
        out = run_command(f"aws elbv2 describe-target-health --target-group-arn {tg_arn}")
        print(f"[register_targets] describe-target-health for {tg_arn}:\n{out}")
    except Exception as e:
        print(f"[register_targets] describe-target-health failed: {e}")

# -------------------------
# Helper: choose port based on TG name heuristic
# -------------------------
def choose_frontend_port_for_tg(tg_arn):
    if not tg_arn:
        return FRONTEND_BLUE_PORT
    name = tg_arn.lower()
    if "green" in name:
        return FRONTEND_GREEN_PORT
    if "blue" in name:
        return FRONTEND_BLUE_PORT
    # default fallback
    return FRONTEND_BLUE_PORT

def choose_backend_port_for_tg(tg_arn):
    if not tg_arn:
        return BACKEND_BLUE_PORT
    name = tg_arn.lower()
    if "green" in name:
        return BACKEND_GREEN_PORT
    if "blue" in name:
        return BACKEND_BLUE_PORT
    return BACKEND_BLUE_PORT

# -------------------------
# Main rollback flow
# -------------------------
def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--outputs-json", required=True)
    args = p.parse_args()

    # infra json
    with open(args.outputs_json) as fh:
        infra = json.load(fh)
    listener_arn = infra.get("alb_listener_arn", "")

    # envs / creds
    pem_path = os.path.expanduser(os.getenv("PEM_PATH", "")) or None
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION")

    # worker
    worker_status = os.getenv("WORKER_STATUS", "").lower()
    worker_instance_ids = os.getenv("WORKER_INSTANCE_IDS", "")

    # backend
    backend_status = os.getenv("BACKEND_STATUS", "").lower()
    backend_inactive_tg = os.getenv("BACKEND_INACTIVE_TG", "")
    backend_instance_ids = os.getenv("BACKEND_INSTANCE_IDS", "")

    # frontend (we'll still register targets by default; you said you'll handle frontend but we include it)
    frontend_status = os.getenv("FRONTEND_STATUS", "").lower()
    frontend_inactive_tg = os.getenv("FRONTEND_INACTIVE_TG", "")
    frontend_instance_ids = os.getenv("FRONTEND_INSTANCE_IDS", "")

    print("[rollback] Starting rollback metadata job")

    # Worker rollback (rename worker_new -> worker) if prepared
    try:
        if worker_status == "prepared":
            print("[rollback] Worker status=prepared -> performing worker rollback (rename).")
            rollback_worker(worker_instance_ids, pem_path, aws_access_key, aws_secret_key, aws_region)
        else:
            print(f"[rollback] Worker status={worker_status} -> skipping worker rollback.")
    except Exception as e:
        print(f"[rollback] Worker rollback ERROR: {e}")

    # Backend: create/update rules pointing to inactive TG, then register instances into that TG
    try:
        if backend_status == "prepared":
            print("[rollback] Backend status=prepared -> creating/updating rules and registering targets")
            backend_paths = ["/api/aws/*", "/api/azure/*", "/api/gcp/*"]
            priority = 10
            for path in backend_paths:
                create_or_update_rule(listener_arn, path, backend_inactive_tg, priority, "Backend")
                priority += 1
            # register instances to inactive TG
            backend_port = choose_backend_port_for_tg(backend_inactive_tg)
            print(f"[rollback] Registering backend instances to {backend_inactive_tg} on port {backend_port}")
            register_targets_to_tg(backend_inactive_tg, backend_instance_ids, backend_port)
        else:
            print(f"[rollback] Backend status={backend_status} -> skipping backend rollback.")
    except Exception as e:
        print(f"[rollback] Backend rollback ERROR: {e}")

    # Frontend: (optional) create/update rules & register instances to inactive TG
    try:
        if frontend_status == "prepared":
            print("[rollback] Frontend status=prepared -> creating/updating rules and registering targets")
            frontend_paths = ["/", "/favicon.ico", "/robots.txt", "/static/*"]
            priority = 500
            for path in frontend_paths:
                create_or_update_rule(listener_arn, path, frontend_inactive_tg, priority, "Frontend")
                priority += 1
            frontend_port = choose_frontend_port_for_tg(frontend_inactive_tg)
            print(f"[rollback] Registering frontend instances to {frontend_inactive_tg} on port {frontend_port}")
            register_targets_to_tg(frontend_inactive_tg, frontend_instance_ids, frontend_port)
        else:
            print(f"[rollback] Frontend status={frontend_status} -> skipping frontend rollback.")
    except Exception as e:
        print(f"[rollback] Frontend rollback ERROR: {e}")

    print("\n=== Rollback metadata script completed ===")

if __name__ == "__main__":
    main()
