#!/usr/bin/env python3
"""
Rollback metadata job (updated)
- detects TG target type (instance/ip)
- uses private IPs for ip-type TGs
- deletes rules referencing TGs (handles both TargetGroupArn and ForwardConfig styles)
- deregisters/registers targets and waits + logs describe-target-health details on failure
- prints health-check configuration for TGs
"""

import argparse
import os
import json
import subprocess
import time
import boto3
import paramiko

# -------------------------------------------------------------------
# Constants: Hardcoded ports
# -------------------------------------------------------------------
FRONTEND_BLUE_PORT = "3000"
FRONTEND_GREEN_PORT = "3001"
BACKEND_BLUE_PORT = "8080"
BACKEND_GREEN_PORT = "8081"

# -------------------------------------------------------------------
# Logging + runner (shell)
# -------------------------------------------------------------------
def log(msg: str):
    print(f"[rollback-metadata] {msg}", flush=True)

def run(cmd: list[str]) -> str:
    """Run a shell aws CLI command and log stdout/stderr. Raises on non-zero exit."""
    log(f"[run] START → {' '.join(cmd)}")
    start = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = round(time.time() - start, 2)
    if res.returncode != 0:
        log(f"[run] ERROR ({elapsed}s) STDERR: {res.stderr.strip()}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    log(f"[run] SUCCESS ({elapsed}s) {('-- had stdout --' if res.stdout.strip() else '')}")
    if res.stdout.strip():
        log(f"[run] STDOUT: {res.stdout.strip()}")
    return res.stdout.strip()

# -------------------------------------------------------------------
# Worker rollback helpers
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
# ALB helpers (robust)
# -------------------------------------------------------------------
def get_tg_description(tg_arn: str) -> dict:
    """Return parsed target-group description (via aws cli)"""
    out = run(["aws", "elbv2", "describe-target-groups", "--target-group-arn", tg_arn])
    js = json.loads(out)
    tgs = js.get("TargetGroups", [])
    if not tgs:
        raise RuntimeError(f"No target group found for {tg_arn}")
    return tgs[0]

def get_target_type(tg_arn: str) -> str:
    tg = get_tg_description(tg_arn)
    tt = tg.get("TargetType", "instance")
    log(f"[tg] {tg_arn} TargetType={tt}")
    return tt

def get_health_check_info(tg_arn: str) -> dict:
    tg = get_tg_description(tg_arn)
    return {
        "protocol": tg.get("HealthCheckProtocol"),
        "port": tg.get("HealthCheckPort"),
        "path": tg.get("HealthCheckPath"),
        "matcher": tg.get("Matcher", {}),
        "interval_seconds": tg.get("HealthCheckIntervalSeconds"),
        "timeout_seconds": tg.get("HealthCheckTimeoutSeconds"),
        "healthy_threshold": tg.get("HealthyThresholdCount"),
        "unhealthy_threshold": tg.get("UnhealthyThresholdCount")
    }

def describe_target_health_verbose(tg_arn: str) -> dict:
    out = run(["aws", "elbv2", "describe-target-health", "--target-group-arn", tg_arn])
    return json.loads(out)

def deregister_targets(tg_arn: str, ids: list[str], aws_region: str = None):
    if not tg_arn or not ids:
        log(f"[deregister_targets] skipping: tg_arn or ids empty. tg_arn={tg_arn}, ids={ids}")
        return
    log(f"[deregister_targets] Deregistering targets {ids} from {tg_arn}")
    targets = [f"Id={i}" for i in ids if i]
    try:
        run(["aws", "elbv2", "deregister-targets", "--target-group-arn", tg_arn, "--targets"] + targets)
    except Exception as e:
        log(f"[deregister_targets] Warning: deregister failed: {e}")

def delete_rules(listener_arn: str, tg_arn: str):
    if not listener_arn or not tg_arn:
        log("[delete_rules] listener_arn or tg_arn missing, skipping deletion")
        return
    log(f"[delete_rules] Looking for rules referencing TG {tg_arn} on listener {listener_arn}")
    rules_json = run(["aws", "elbv2", "describe-rules", "--listener-arn", listener_arn])
    rules = json.loads(rules_json).get("Rules", [])
    for r in rules:
        arn = r.get("RuleArn")
        actions = r.get("Actions", [])
        should_delete = False
        for a in actions:
            # direct TargetGroupArn
            if a.get("TargetGroupArn") == tg_arn:
                should_delete = True
                break
            # ForwardConfig style
            fwd = a.get("ForwardConfig", {})
            for tg in fwd.get("TargetGroups", []):
                if tg.get("TargetGroupArn") == tg_arn:
                    should_delete = True
                    break
            if should_delete:
                break
        if should_delete and arn:
            log(f"[delete_rules] Deleting rule {arn} referencing {tg_arn}")
            try:
                run(["aws", "elbv2", "delete-rule", "--rule-arn", arn])
            except Exception as e:
                log(f"[delete_rules] Failed to delete rule {arn}: {e}")

def create_rule(listener_arn: str, tg_arn: str, path: str, priority: int):
    if not listener_arn or not tg_arn:
        log(f"[create_rule] missing listener or tg (listener={listener_arn}, tg={tg_arn})")
        return
    log(f"[create_rule] Creating rule: path={path}, tg={tg_arn}, priority={priority}")
    run([
        "aws", "elbv2", "create-rule",
        "--listener-arn", listener_arn,
        "--priority", str(priority),
        "--conditions", f"Field=path-pattern,Values={path}",
        "--actions", f"Type=forward,TargetGroupArn={tg_arn}"
    ])

def _resolve_private_ips_for_instances(instance_ids: list[str], aws_region: str) -> list[str]:
    """Return list of primary private IPs for the provided instances (in same order as instance_ids when possible)."""
    if not instance_ids:
        return []
    ec2 = boto3.client("ec2", region_name=aws_region)
    ips = []
    # describe-instances may return instances in any order; map by id
    resp = ec2.describe_instances(InstanceIds=instance_ids)
    id_to_ip = {}
    for r in resp.get("Reservations", []):
        for inst in r.get("Instances", []):
            iid = inst.get("InstanceId")
            # find primary private IPv4
            priv_ip = inst.get("PrivateIpAddress")
            if not priv_ip:
                # try network interfaces
                for iface in inst.get("NetworkInterfaces", []):
                    for p in iface.get("PrivateIpAddresses", []):
                        if p.get("Primary"):
                            priv_ip = p.get("PrivateIpAddress")
                            break
                    if priv_ip:
                        break
            if priv_ip:
                id_to_ip[iid] = priv_ip
    # preserve order of instance_ids
    for iid in instance_ids:
        if iid in id_to_ip:
            ips.append(id_to_ip[iid])
        else:
            log(f"[resolve_ips] WARNING: couldn't find private IP for instance {iid}")
    return ips

def register_targets(tg_arn: str, instance_ids: list[str], port: str, aws_region: str, wait_seconds: int = 60):
    if not tg_arn or not instance_ids:
        log(f"[register_targets] skipping: tg_arn or instance_ids empty (tg={tg_arn}, ids={instance_ids})")
        return

    tt = get_target_type(tg_arn)
    log(f"[register_targets] TG={tg_arn} targetType={tt}")

    if tt == "ip":
        ips = _resolve_private_ips_for_instances(instance_ids, aws_region)
        if not ips:
            raise RuntimeError("[register_targets] No private IPs found for instances; cannot register to ip-type TG")
        targets = [f"Id={ip},Port={port}" for ip in ips]
        ids_used = ips
        log(f"[register_targets] Registering IPs {ips} -> {tg_arn}:{port}")
    else:
        targets = [f"Id={iid},Port={port}" for iid in instance_ids]
        ids_used = instance_ids
        log(f"[register_targets] Registering Instance IDs {instance_ids} -> {tg_arn}:{port}")

    # register
    run(["aws", "elbv2", "register-targets", "--target-group-arn", tg_arn, "--targets"] + targets)

    # wait & verify health
    healthy = wait_for_targets_healthy_verbose(tg_arn, ids_used, timeout_seconds=wait_seconds)
    if not healthy:
        log(f"[register_targets] WARNING: Targets did not become healthy within {wait_seconds}s for TG {tg_arn}")
        dump = describe_target_health_verbose(tg_arn)
        log(f"[register_targets] describe-target-health: {json.dumps(dump, indent=2)}")

def wait_for_targets_healthy_verbose(tg_arn: str, ids: list[str], timeout_seconds: int = 60):
    """Poll describe-target-health and return True if all provided ids appear and are healthy."""
    log(f"[wait] Waiting up to {timeout_seconds}s for targets {ids} in {tg_arn} to be healthy")
    deadline = time.time() + timeout_seconds
    last_states = {}
    while time.time() < deadline:
        try:
            out = run(["aws", "elbv2", "describe-target-health", "--target-group-arn", tg_arn])
            desc = json.loads(out).get("TargetHealthDescriptions", [])
            last_states = {}
            for d in desc:
                tgt = d.get("Target", {})
                tid = tgt.get("Id")
                th = d.get("TargetHealth", {})
                state = th.get("State", "unknown")
                reason = th.get("Reason")
                description = th.get("Description")
                last_states[tid] = {"state": state, "reason": reason, "description": description}
            # check all ids present and healthy
            all_present = all(i in last_states for i in ids)
            all_healthy = all(last_states.get(i, {}).get("state") == "healthy" for i in ids if i in last_states)
            log(f"[wait] observed states: {last_states}")
            if all_present and all_healthy:
                log(f"[wait] All targets healthy for TG {tg_arn}")
                return True
        except Exception as e:
            log(f"[wait] describe-target-health failed: {e}")
        time.sleep(3)
    log(f"[wait] Timeout, last observed states: {last_states}")
    return False

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
        log("[info] deployment.json loaded (not used further)")

    components = [c.strip().lower() for c in args.components]
    if "all" in components:
        components = ["worker", "backend", "frontend"]
    log(f"[info] Components selected for rollback: {components}")

    listener_arn = infra.get("alb_listener_arn")
    aws_region = os.getenv("AWS_REGION")
    pem_path = os.path.expanduser(os.getenv("PEM_PATH", "")) or None
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

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
            # determine port by active env name presence
            if active:
                port = BACKEND_GREEN_PORT if "blue" in active.lower() else BACKEND_BLUE_PORT
            else:
                port = BACKEND_BLUE_PORT
            # diagnostics: log health-check config
            if active:
                try:
                    hc = get_health_check_info(active)
                    log(f"[backend] Active TG health-check: {hc}")
                except Exception as e:
                    log(f"[backend] failed to get health-check for active TG: {e}")
            if inactive:
                try:
                    hc = get_health_check_info(inactive)
                    log(f"[backend] Inactive TG health-check: {hc}")
                except Exception as e:
                    log(f"[backend] failed to get health-check for inactive TG: {e}")

            delete_rules(listener_arn, active)
            deregister_targets(active, ids, aws_region)
            register_targets(inactive, ids, port, aws_region)

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

            if active:
                try:
                    hc = get_health_check_info(active)
                    log(f"[frontend] Active TG health-check: {hc}")
                except Exception as e:
                    log(f"[frontend] failed to get health-check for active TG: {e}")
            if inactive:
                try:
                    hc = get_health_check_info(inactive)
                    log(f"[frontend] Inactive TG health-check: {hc}")
                except Exception as e:
                    log(f"[frontend] failed to get health-check for inactive TG: {e}")

            # choose port for inactive TG by naming heuristic
            port = FRONTEND_GREEN_PORT if "blue" in (active or "").lower() else FRONTEND_BLUE_PORT

            delete_rules(listener_arn, active)
            deregister_targets(active, ids, aws_region)
            register_targets(inactive, ids, port, aws_region)

            frontend_paths = ["/", "/favicon.ico", "/robots.txt", "/static/*"]
            prio = 500
            for path in frontend_paths:
                create_rule(listener_arn, inactive, path, prio)
                prio += 1

        handle_component("frontend", os.getenv("FRONTEND_STATUS", ""), os.getenv("FRONTEND_FIRST_DEPLOYMENT", "false"), frontend_rollback)

if __name__ == "__main__":
    main()
