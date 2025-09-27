#!/usr/bin/env python3
import argparse
import os
import json
import subprocess
import time
import paramiko
import boto3

# -------------------------------------------------------------------
# Constants: Hardcoded ports (same as your deploy)
# -------------------------------------------------------------------
FRONTEND_BLUE_PORT = "3000"
FRONTEND_GREEN_PORT = "3001"
BACKEND_BLUE_PORT = "8080"
BACKEND_GREEN_PORT = "8081"

# -------------------------------------------------------------------
# Logging + runner
# -------------------------------------------------------------------
def log(msg):
    print(f"[rollback-metadata] {msg}", flush=True)

def run(cmd):
    """Run a shell command (cmd as list) and return stdout, raising on non-zero exit."""
    log(f"[run] START → {' '.join(cmd)}")
    start = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = round(time.time() - start, 2)
    if res.returncode != 0:
        log(f"[run] ERROR ({elapsed}s): {res.stderr.strip()}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    log(f"[run] SUCCESS ({elapsed}s)")
    if res.stdout and res.stdout.strip():
        log(f"[run] STDOUT: {res.stdout.strip()}")
    return res.stdout.strip()

# -------------------------------------------------------------------
# Worker rollback (rename worker_new → worker)
# -------------------------------------------------------------------
def rename_worker_on_instance(instance_ip, pem_path):
    log(f"Renaming worker_new → worker on {instance_ip}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(instance_ip, username="ec2-user", key_filename=pem_path)
    # Keep your exact operations
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

    # instance_ids is expected as a list
    reservations = ec2.describe_instances(InstanceIds=instance_ids)["Reservations"]
    for res in reservations:
        for inst in res["Instances"]:
            ip = inst.get("PublicIpAddress")
            if ip:
                try:
                    rename_worker_on_instance(ip, pem_path)
                except Exception as e:
                    log(f"[worker] Error on {ip}: {e}")
            else:
                log(f"[worker] Instance {inst['InstanceId']} has no public IP, skipping.")

# -------------------------------------------------------------------
# ALB helpers: target-type aware register, and create-or-update rule
# -------------------------------------------------------------------
def get_tg_description(tg_arn):
    """Return target-group JSON from AWS CLI"""
    out = run(["aws", "elbv2", "describe-target-groups", "--target-group-arn", tg_arn])
    js = json.loads(out)
    tgs = js.get("TargetGroups", [])
    if not tgs:
        raise RuntimeError(f"No target group found for {tg_arn}")
    return tgs[0]

def get_target_type(tg_arn):
    tg = get_tg_description(tg_arn)
    tt = tg.get("TargetType", "instance")
    log(f"[tg] {tg_arn} TargetType={tt}")
    return tt

def _resolve_private_ips_for_instances(instance_ids, aws_region):
    """Return list of primary private IPs for provided instance_ids (preserve order where possible)."""
    if not instance_ids:
        return []
    ec2 = boto3.client("ec2", region_name=aws_region)
    resp = ec2.describe_instances(InstanceIds=instance_ids)
    id_to_ip = {}
    for r in resp.get("Reservations", []):
        for inst in r.get("Instances", []):
            iid = inst.get("InstanceId")
            priv_ip = inst.get("PrivateIpAddress")
            if not priv_ip:
                # fallback to network interfaces
                for iface in inst.get("NetworkInterfaces", []):
                    for p in iface.get("PrivateIpAddresses", []):
                        if p.get("Primary"):
                            priv_ip = p.get("PrivateIpAddress")
                            break
                    if priv_ip:
                        break
            if priv_ip:
                id_to_ip[iid] = priv_ip
    ips = []
    for iid in instance_ids:
        if iid in id_to_ip:
            ips.append(id_to_ip[iid])
        else:
            log(f"[resolve_ips] WARNING: private IP not found for instance {iid}")
    return ips

def register_targets(tg_arn, instance_ids, port, aws_region):
    """
    Register instance_ids to tg_arn on given port.
    If TG target type is 'ip', resolve private IPs and register them.
    instance_ids must be a list of instance IDs.
    """
    if not tg_arn or not instance_ids:
        log("[register_targets] Nothing to do (tg_arn or instance_ids missing).")
        return

    tt = get_target_type(tg_arn)
    if tt == "ip":
        ips = _resolve_private_ips_for_instances(instance_ids, aws_region)
        if not ips:
            raise RuntimeError("[register_targets] No private IPs resolved for instances; cannot register to ip-type TG.")
        targets = [f"Id={ip},Port={port}" for ip in ips]
        ids_used = ips
        log(f"[register_targets] Registering IPs {ips} -> {tg_arn}:{port}")
    else:
        targets = [f"Id={iid},Port={port}" for iid in instance_ids]
        ids_used = instance_ids
        log(f"[register_targets] Registering instance IDs {instance_ids} -> {tg_arn}:{port}")

    run(["aws", "elbv2", "register-targets", "--target-group-arn", tg_arn, "--targets"] + targets)

    # Brief pause, then describe-target-health for visibility
    time.sleep(2)
    try:
        out = run(["aws", "elbv2", "describe-target-health", "--target-group-arn", tg_arn])
        log(f"[register_targets] describe-target-health for {tg_arn}:\n{out}")
    except Exception as e:
        log(f"[register_targets] describe-target-health failed: {e}")

def create_or_update_rule(listener_arn, path, target_group_arn, priority, service_name):
    """
    If a rule exists for `path` (path-pattern match) then modify it to forward to target_group_arn.
    Otherwise create a new rule with given priority.
    This mirrors your deploy_service() behavior.
    """
    if not target_group_arn:
        log(f"[create_or_update_rule] Skipping ALB rule for {service_name} path '{path}': target group missing.")
        return
    log(f"[create_or_update_rule] Processing ALB rule for {service_name}: path='{path}' -> TG='{target_group_arn}'")
    # Query for any rule whose path-pattern condition contains the path
    # (mirror deploy script's query)
    try:
        rule_arn = run([
            "aws", "elbv2", "describe-rules",
            "--listener-arn", listener_arn,
            "--query", f"Rules[?Conditions[?Field=='path-pattern' && contains(Values,'{path}')]].RuleArn",
            "--output", "text"
        ]) or ""
    except Exception as e:
        log(f"[create_or_update_rule] describe-rules failed: {e}")
        rule_arn = ""

    if not rule_arn or rule_arn == "None":
        log(f"[create_or_update_rule] Creating new ALB rule for {service_name} path '{path}'")
        run([
            "aws", "elbv2", "create-rule",
            "--listener-arn", listener_arn,
            "--priority", str(priority),
            "--conditions", f"Field=path-pattern,Values={path}",
            "--actions", f"Type=forward,TargetGroupArn={target_group_arn}"
        ])
    else:
        log(f"[create_or_update_rule] Modifying existing ALB rule {rule_arn} for path '{path}'")
        run([
            "aws", "elbv2", "modify-rule",
            "--rule-arn", rule_arn,
            "--conditions", f"Field=path-pattern,Values={path}",
            "--actions", f"Type=forward,TargetGroupArn={target_group_arn}"
        ])

# -------------------------------------------------------------------
# Component handler (keeps your original semantics)
# -------------------------------------------------------------------
def handle_component(name, status, first_deployment, rollback_fn=None):
    log(f"--- Handling {name.upper()} ---")

    if first_deployment.lower() == "true":
        if status == "cleaned":
            log(f"[{name}] First deployment detected. No rollback needed; already in baseline state.")
        else:
            log(f"[{name}] First deployment detected but deployment failed (status={status}). No rollback performed.")
        return

    if first_deployment.lower() == "false":
        if status == "prepared":
            log(f"[{name}] Rollback required (status=prepared).")
            if rollback_fn:
                rollback_fn()
            log(f"[{name}] Rollback finalized.")
        elif status == "cleaned":
            log(f"[{name}] Rollback not needed. Already cleaned.")
        elif not status:
            log(f"[{name}] Skipping rollback. No status provided.")
        else:
            log(f"[{name}] Skipping rollback. Status={status}.")

# -------------------------------------------------------------------
# Main orchestration
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
        try:
            with open(args.deployment_json) as f:
                _ = json.load(f)
            log("[info] Deployment.json loaded (not heavily used).")
        except Exception as e:
            log(f"[info] Failed to load deployment.json: {e}")

    components = [c.strip().lower() for c in args.components]
    if "all" in components:
        components = ["worker", "backend", "frontend"]
    log(f"[info] Components selected for rollback: {components}")

    listener_arn = infra.get("alb_listener_arn")
    pem_path = os.path.expanduser(os.getenv("PEM_PATH", "")) or None
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION")

    if not (aws_access_key and aws_secret_key and aws_region):
        log("[error] Missing AWS credentials or region in environment.")
        return

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
    else:
        log("[worker] Not selected in components, skipping.")

    # Backend: register targets to inactive TG first, then create/update rules
    if "backend" in components:
        def backend_rollback():
            tg_inactive = os.getenv("BACKEND_INACTIVE_TG", "")
            instance_ids = [i for i in os.getenv("BACKEND_INSTANCE_IDS", "").split(",") if i]
            if not tg_inactive:
                log("[backend] No BACKEND_INACTIVE_TG provided; skipping backend rollback.")
                return
            if not instance_ids:
                log("[backend] No BACKEND_INSTANCE_IDS provided; skipping registration.")
            # determine port from tg naming heuristic
            port = BACKEND_GREEN_PORT if "green" in tg_inactive.lower() else BACKEND_BLUE_PORT
            # register targets first
            try:
                register_targets(tg_inactive, instance_ids, port, aws_region)
            except Exception as e:
                log(f"[backend] register_targets failed: {e}")
            # then ensure rules point to inactive TG (create or modify)
            backend_paths = ["/api/aws/*", "/api/azure/*", "/api/gcp/*"]
            prio = 10
            for path in backend_paths:
                try:
                    create_or_update_rule(listener_arn, path, tg_inactive, prio, "Backend")
                except Exception as e:
                    log(f"[backend] create_or_update_rule failed for path {path}: {e}")
                prio += 1

        handle_component("backend", os.getenv("BACKEND_STATUS", ""), os.getenv("BACKEND_FIRST_DEPLOYMENT", "false"), backend_rollback)
    else:
        log("[backend] Not selected in components, skipping.")

    # Frontend: register targets to inactive TG first, then create/update rules
    if "frontend" in components:
        def frontend_rollback():
            tg_inactive = os.getenv("FRONTEND_INACTIVE_TG", "")
            instance_ids = [i for i in os.getenv("FRONTEND_INSTANCE_IDS", "").split(",") if i]
            if not tg_inactive:
                log("[frontend] No FRONTEND_INACTIVE_TG provided; skipping frontend rollback.")
                return
            if not instance_ids:
                log("[frontend] No FRONTEND_INSTANCE_IDS provided; skipping registration.")
            # determine port from tg naming heuristic
            port = FRONTEND_GREEN_PORT if "green" in tg_inactive.lower() else FRONTEND_BLUE_PORT
            # register targets first
            try:
                register_targets(tg_inactive, instance_ids, port, aws_region)
            except Exception as e:
                log(f"[frontend] register_targets failed: {e}")
            # then create/update rules
            frontend_paths = ["/", "/favicon.ico", "/robots.txt", "/static/*"]
            prio = 500
            for path in frontend_paths:
                try:
                    create_or_update_rule(listener_arn, path, tg_inactive, prio, "Frontend")
                except Exception as e:
                    log(f"[frontend] create_or_update_rule failed for path {path}: {e}")
                prio += 1

        handle_component("frontend", os.getenv("FRONTEND_STATUS", ""), os.getenv("FRONTEND_FIRST_DEPLOYMENT", "false"), frontend_rollback)
    else:
        log("[frontend] Not selected in components, skipping.")

    log("Rollback metadata job completed.")

if __name__ == "__main__":
    main()
