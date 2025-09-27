#!/usr/bin/env python3
import argparse
import os
import json
import subprocess
import time
import paramiko
import boto3

# -------------------------------------------------------------------
# Constants: Hardcoded ports
# -------------------------------------------------------------------
FRONTEND_BLUE_PORT = "3000"
FRONTEND_GREEN_PORT = "3001"
BACKEND_BLUE_PORT = "8080"
BACKEND_GREEN_PORT = "8081"

# -------------------------------------------------------------------
# Logging + runner
# -------------------------------------------------------------------
def log(msg: str):
    print(f"[rollback-metadata] {msg}", flush=True)

def run(cmd: list[str]) -> str:
    log(f"[run] START → {' '.join(cmd)}")
    start = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = round(time.time() - start, 2)
    if res.returncode != 0:
        log(f"[run] ERROR ({elapsed}s): {res.stderr.strip()}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    log(f"[run] SUCCESS ({elapsed}s)")
    if res.stdout.strip():
        log(f"[run] STDOUT: {res.stdout.strip()}")
    return res.stdout.strip()

# -------------------------------------------------------------------
# Worker rollback
# -------------------------------------------------------------------
def rename_worker_on_instance(instance_ip, pem_path):
    log(f"Renaming worker_new → worker on {instance_ip}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(instance_ip, username="ec2-user", key_filename=pem_path)
    ssh.exec_command("docker rm -f worker || true")
    ssh.exec_command("docker rename worker_new worker || true")
    ssh.close()
    log(f"[{instance_ip}] Worker container rollback finalized.")

def rollback_worker(instance_ids, pem_path, aws_access_key, aws_secret_key, aws_region):
    if not instance_ids:
        log("[worker] No instance IDs provided, skipping rollback.")
        return
    if not pem_path:
        log("[worker] PEM_PATH not set, skipping worker rollback.")
        return

    ec2 = boto3.client(
        "ec2",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )

    reservations = ec2.describe_instances(InstanceIds=instance_ids)["Reservations"]
    for res in reservations:
        for inst in res["Instances"]:
            ip = inst.get("PublicIpAddress")
            if ip:
                rename_worker_on_instance(ip, pem_path)
            else:
                log(f"[worker] Instance {inst['InstanceId']} has no public IP, skipping.")

# -------------------------------------------------------------------
# ALB helpers
# -------------------------------------------------------------------
def deregister_targets(tg_arn: str, ids: list[str]):
    if not tg_arn or not ids:
        return
    log(f"Deregistering {ids} from {tg_arn}")
    targets = [f"Id={i}" for i in ids if i]
    run(["aws", "elbv2", "deregister-targets", "--target-group-arn", tg_arn, "--targets"] + targets)

def register_targets(tg_arn: str, ids: list[str], port: str):
    if not tg_arn or not ids:
        return
    log(f"Registering {ids} into {tg_arn} on port {port}")
    if not port:
        raise RuntimeError(f"[register_targets] Port is missing for TG {tg_arn}")
    targets = [f"Id={i},Port={port}" for i in ids if i]
    run(["aws", "elbv2", "register-targets", "--target-group-arn", tg_arn, "--targets"] + targets)

def delete_rules(listener_arn: str, tg_arn: str):
    if not listener_arn or not tg_arn:
        return
    rules_json = run(["aws", "elbv2", "describe-rules", "--listener-arn", listener_arn])
    rules = json.loads(rules_json).get("Rules", [])
    for r in rules:
        for a in r.get("Actions", []):
            fwd_cfg = a.get("ForwardConfig", {})
            for tg in fwd_cfg.get("TargetGroups", []):
                if tg.get("TargetGroupArn") == tg_arn:
                    arn = r["RuleArn"]
                    log(f"Deleting rule {arn} (TG={tg_arn})")
                    run(["aws", "elbv2", "delete-rule", "--rule-arn", arn])

def create_rule(listener_arn: str, tg_arn: str, path: str, priority: int):
    if not listener_arn or not tg_arn:
        return
    log(f"Creating rule path={path}, TG={tg_arn}, priority={priority}")
    run([
        "aws", "elbv2", "create-rule",
        "--listener-arn", listener_arn,
        "--priority", str(priority),
        "--conditions", f"Field=path-pattern,Values={path}",
        "--actions", f"Type=forward,TargetGroupArn={tg_arn}"
    ])

# -------------------------------------------------------------------
# Component handling
# -------------------------------------------------------------------
def handle_component(name, status, first_deployment, rollback_fn=None):
    log(f"--- Handling {name.upper()} ---")
    if first_deployment.lower() == "true":
        if status == "cleaned":
            log(f"[{name}] First deployment detected. No rollback needed.")
        else:
            log(f"[{name}] First deployment failed (status={status}). No rollback performed.")
        return

    if status == "prepared":
        log(f"[{name}] Rollback required (status=prepared).")
        if rollback_fn:
            rollback_fn()
        log(f"[{name}] Rollback finalized.")
    elif status == "cleaned":
        log(f"[{name}] Already cleaned. No rollback.")
    elif not status:
        log(f"[{name}] No status provided. Skipping rollback.")
    else:
        log(f"[{name}] Status={status}. Skipping rollback.")

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--infra-json", required=True)
    p.add_argument("--deployment-json", required=False)
    p.add_argument("--components", required=True, nargs="+")
    args = p.parse_args()

    with open(args.infra_json) as f:
        infra = json.load(f)

    if args.deployment_json:
        with open(args.deployment_json) as f:
            _ = json.load(f)
        log("[info] Deployment.json loaded.")

    components = [c.strip().lower() for c in args.components]
    if "all" in components:
        components = ["worker", "backend", "frontend"]
    log(f"[info] Components selected for rollback: {components}")

    listener_arn = infra.get("alb_listener_arn")
    pem_path = os.path.expanduser(os.getenv("PEM_PATH", "")) or None
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION")

    # Worker
    if "worker" in components:
        handle_component(
            "worker",
            os.getenv("WORKER_STATUS", ""),
            os.getenv("WORKER_FIRST_DEPLOYMENT", "false"),
            rollback_fn=lambda: rollback_worker(
                [i for i in os.getenv("WORKER_INSTANCE_IDS", "").split(",") if i],
                pem_path, aws_access_key, aws_secret_key, aws_region
            )
        )

    # Backend
    if "backend" in components:
        def backend_rollback():
            active = os.getenv("BACKEND_ACTIVE_TG", "")
            inactive = os.getenv("BACKEND_INACTIVE_TG", "")
            ids = [i for i in os.getenv("BACKEND_INSTANCE_IDS", "").split(",") if i]

            # choose port for inactive TG
            port = BACKEND_GREEN_PORT if "blue" in active.lower() else BACKEND_BLUE_PORT

            delete_rules(listener_arn, active)
            deregister_targets(active, ids)
            register_targets(inactive, ids, port)

            backend_paths = ["/api/aws/*", "/api/azure/*", "/api/gcp/*"]
            prio = 10
            for path in backend_paths:
                create_rule(listener_arn, inactive, path, prio)
                prio += 1

        handle_component("backend", os.getenv("BACKEND_STATUS", ""), os.getenv("BACKEND_FIRST_DEPLOYMENT", "false"), backend_rollback)

    # Frontend
    if "frontend" in components:
        def frontend_rollback():
            active = os.getenv("FRONTEND_ACTIVE_TG", "")
            inactive = os.getenv("FRONTEND_INACTIVE_TG", "")
            ids = [i for i in os.getenv("FRONTEND_INSTANCE_IDS", "").split(",") if i]

            # choose port for inactive TG
            port = FRONTEND_GREEN_PORT if "blue" in active.lower() else FRONTEND_BLUE_PORT

            delete_rules(listener_arn, active)
            deregister_targets(active, ids)
            register_targets(inactive, ids, port)

            frontend_paths = ["/", "/favicon.ico", "/robots.txt", "/static/*"]
            prio = 500
            for path in frontend_paths:
                create_rule(listener_arn, inactive, path, prio)
                prio += 1

        handle_component("frontend", os.getenv("FRONTEND_STATUS", ""), os.getenv("FRONTEND_FIRST_DEPLOYMENT", "false"), frontend_rollback)

if __name__ == "__main__":
    main()
