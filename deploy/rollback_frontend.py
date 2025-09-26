#!/usr/bin/env python3
import argparse
import os
import json
import subprocess
import time
import paramiko
import boto3


# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
def log(msg: str):
    print(f"[rollback-metadata] {msg}", flush=True)


def run(cmd: list[str]) -> str:
    """Run a shell command and capture stdout"""
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
# Worker rollback (rename worker_new → worker)
# -------------------------------------------------------------------
def rename_worker_on_instance(instance_ip, pem_path):
    """SSH into instance and rename worker_new → worker"""
    log(f"Renaming worker_new → worker on {instance_ip}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(instance_ip, username="ec2-user", key_filename=pem_path)

    ssh.exec_command("docker rm -f worker || true")
    ssh.exec_command("docker rename worker_new worker || true")

    ssh.close()
    log(f"[{instance_ip}] Worker container rollback finalized.")


def rollback_worker(instance_ids, pem_path, aws_access_key, aws_secret_key, aws_region):
    """Rename worker_new to worker on all instances"""
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
# ALB Helpers for backend/frontend
# -------------------------------------------------------------------
def deregister_targets(tg_arn: str, ids: list[str]):
    if not tg_arn or not ids:
        log("[deregister_targets] Nothing to do.")
        return
    log(f"Deregistering {ids} from {tg_arn}")
    targets = [f"Id={i}" for i in ids]
    run(["aws", "elbv2", "deregister-targets",
         "--target-group-arn", tg_arn,
         "--targets"] + targets)
    run(["aws", "elbv2", "wait", "target-deregistered",
         "--target-group-arn", tg_arn,
         "--targets"] + targets)


def register_targets(tg_arn: str, ids: list[str]):
    if not tg_arn or not ids:
        log("[register_targets] Nothing to do.")
        return
    log(f"Registering {ids} into {tg_arn}")
    targets = [f"Id={i}" for i in ids]
    run(["aws", "elbv2", "register-targets",
         "--target-group-arn", tg_arn,
         "--targets"] + targets)
    run(["aws", "elbv2", "wait", "target-in-service",
         "--target-group-arn", tg_arn,
         "--targets"] + targets)


def delete_rules(listener_arn: str, tg_arn: str):
    if not listener_arn or not tg_arn:
        log("[delete_rules] Nothing to do.")
        return
    rules_json = run(["aws", "elbv2", "describe-rules",
                      "--listener-arn", listener_arn])
    rules = json.loads(rules_json).get("Rules", [])
    for r in rules:
        for a in r.get("Actions", []):
            for tg in a.get("ForwardConfig", {}).get("TargetGroups", []):
                if tg.get("TargetGroupArn") == tg_arn:
                    arn = r["RuleArn"]
                    log(f"Deleting rule {arn} (TG={tg_arn})")
                    run(["aws", "elbv2", "delete-rule", "--rule-arn", arn])


def create_rule(listener_arn: str, tg_arn: str, path: str, priority: int):
    if not listener_arn or not tg_arn:
        log(f"[create_rule] Skipping path={path}, TG missing")
        return
    log(f"Creating ALB rule: path={path}, TG={tg_arn}, priority={priority}")
    run([
        "aws", "elbv2", "create-rule",
        "--listener-arn", listener_arn,
        "--priority", str(priority),
        "--conditions", f"Field=path-pattern,Values={path}",
        "--actions", f"Type=forward,TargetGroupArn={tg_arn}"
    ])


# -------------------------------------------------------------------
# Main rollback orchestration
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
            deployment = json.load(f)
        log("[info] Deployment.json loaded (not heavily used yet).")

    components = [c.strip().lower() for c in args.components]
    if "all" in components:
        components = ["worker", "backend", "frontend"]

    log(f"[info] Components selected for rollback: {components}")

    listener_arn = infra.get("alb_listener_arn")

    # safer env fetching
    pem_path = os.path.expanduser(os.getenv("PEM_PATH", "")) or None
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION")

    # sanity check
    if not (aws_access_key and aws_secret_key and aws_region):
        log("[error] Missing AWS credentials or region in environment.")
        return

    # Worker envs
    worker_status = os.getenv("worker_status", "")
    worker_instance_ids = [i for i in os.getenv("worker_instance_ids", "").split(",") if i]

    # Backend envs
    backend_status = os.getenv("backend_status", "")
    backend_active_tg = os.getenv("backend_active_tg", "")
    backend_inactive_tg = os.getenv("backend_inactive_tg", "")
    backend_instance_ids = [i for i in os.getenv("backend_instance_ids", "").split(",") if i]

    # Frontend envs
    frontend_status = os.getenv("frontend_status", "")
    frontend_active_tg = os.getenv("frontend_active_tg", "")
    frontend_inactive_tg = os.getenv("frontend_inactive_tg", "")
    frontend_instance_ids = [i for i in os.getenv("frontend_instance_ids", "").split(",") if i]

    # --------------------------------------------------
    # Step 1: Worker rollback (rename)
    # --------------------------------------------------
    if "worker" in components:
        if worker_status == "prepared":
            log("=== Rolling back Worker containers ===")
            rollback_worker(worker_instance_ids, pem_path, aws_access_key, aws_secret_key, aws_region)
        else:
            log("[worker] Skipped (status != prepared)")
    else:
        log("[worker] Not selected in components, skipping.")

    # --------------------------------------------------
    # Step 2: Backend rollback (ALB + TG switch)
    # --------------------------------------------------
    if "backend" in components:
        if backend_status == "prepared":
            log("=== Rolling back Backend ===")
            delete_rules(listener_arn, backend_active_tg)
            deregister_targets(backend_active_tg, backend_instance_ids)
            register_targets(backend_inactive_tg, backend_instance_ids)

            backend_paths = ["/api/aws/*", "/api/azure/*", "/api/gcp/*"]
            priority = 10
            for path in backend_paths:
                create_rule(listener_arn, backend_inactive_tg, path, priority)
                priority += 1
            log("Backend rollback finalized: inactive TG promoted.")
        else:
            log("[backend] Skipped (status != prepared)")
    else:
        log("[backend] Not selected in components, skipping.")

    # --------------------------------------------------
    # Step 3: Frontend rollback (ALB + TG switch)
    # --------------------------------------------------
    if "frontend" in components:
        if frontend_status == "prepared":
            log("=== Rolling back Frontend ===")
            delete_rules(listener_arn, frontend_active_tg)
            deregister_targets(frontend_active_tg, frontend_instance_ids)
            register_targets(frontend_inactive_tg, frontend_instance_ids)

            frontend_paths = ["/", "/favicon.ico", "/robots.txt", "/static/*"]
            priority = 500
            for path in frontend_paths:
                create_rule(listener_arn, frontend_inactive_tg, path, priority)
                priority += 1
            log("Frontend rollback finalized: inactive TG promoted.")
        else:
            log("[frontend] Skipped (status != prepared)")
    else:
        log("[frontend] Not selected in components, skipping.")


if __name__ == "__main__":
    main()
