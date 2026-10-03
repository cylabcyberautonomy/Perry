"""Box agent — the defender's in-environment effector.

Runs as a daemon ON the defender box. The defender's loop (on the harness host, via
RemoteEnvOrchestrator) POSTs host-level actions here; the agent runs the corresponding ansible
playbook LOCALLY — box -> victims, over the defender's scoped key — so no host-level action emanates
from the management host. Infra actions never come here (they go to the environment); the box holds no
cloud credential.

Design:
  * transport: stdlib http.server (no extra dependency on the box), POST /action + GET /health.
  * auth: a per-experiment bearer token (same one the controller holds); every request is checked
    constant-time. The agent binds to the box's address and the deploy step opens its port to the
    controller only — so no other host in the environment can reach it.
  * dispatch (`BoxAgent.handle`) is pure and transport-free, so it is unit-testable; the actual ansible
    execution lives behind an `executor` the agent is constructed with (AnsibleExecutor in production,
    a stub in tests).

Operations (host-level actuators the defender dispatches here):
    BlockIP        -> block_ip.yml against the given target IPs
    ConfigureDecoy -> CheckIfHostUp + InstallSysFlow (+ honey SSH) on an env-created decoy
  (AddFakeData / AddHoneyCredentials / StartHoneyService are registered extension points; they need the
  host's identity (users) serialized from the controller — a follow-up.)
"""
from __future__ import annotations

import hmac
import json
from typing import Callable, Optional


class BoxAgent:
    """Pure auth + dispatch. `executor` provides the concrete ansible operations."""

    def __init__(self, token: str, executor: "Executor"):
        self._token = token or ""
        self._executor = executor
        self._ops: dict[str, Callable[[dict], dict]] = {
            "BlockIP": self._op_block_ip,
            "ConfigureDecoy": self._op_configure_decoy,
            "AddFakeData": self._op_add_fake_data,
            "AddHoneyCredentials": self._op_add_honey_credentials,
            "StartHoneyService": self._op_start_honey_service,
        }

    def handle(self, payload: dict) -> dict:
        token = payload.get("token")
        if not self._token or not isinstance(token, str) or not hmac.compare_digest(token, self._token):
            return {"ok": False, "error": "unauthorized", "status": 403}
        action = payload.get("action") or {}
        kind = action.get("type")
        params = action.get("params") or {}
        op = self._ops.get(kind)
        if op is None:
            return {"ok": False, "error": f"unsupported action {kind!r}", "status": 400}
        try:
            result = op(params) or {}
        except KeyError as e:
            return {"ok": False, "error": f"missing param {e}", "status": 400}
        except Exception as e:  # noqa: BLE001 — a failed action returns an error, never crashes the agent
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "status": 500}
        return {"ok": True, **result, "status": 200}

    # -- operations --------------------------------------------------------
    def _op_block_ip(self, params: dict) -> dict:
        self._executor.block_ip(
            target_ips=params["target_ips"], ip_to_block=params["ip_to_block"], port=params["port"]
        )
        return {"blocked": params["ip_to_block"], "on": len(params["target_ips"])}

    def _op_configure_decoy(self, params: dict) -> dict:
        self._executor.configure_decoy(
            host_ip=params["host_ip"],
            honey_ssh=bool(params.get("honeySSHService", False)),
        )
        return {"configured": params["host_ip"]}

    def _op_add_fake_data(self, params: dict) -> dict:
        import os
        import random
        users = params.get("host_users") or []
        host_user = random.choice(users) if users else "root"
        dst = os.path.join(params.get("path") or "~/", params.get("file_name") or "decoy.json")
        self._executor.add_fake_data(params["host_ip"], host_user, dst, params.get("file_content", "data.json"))
        return {"planted_on": params["host_ip"], "as": host_user}

    def _op_start_honey_service(self, params: dict) -> dict:
        self._executor.start_honey_service(
            params["host_ip"], params.get("port_no", "8000"), params.get("service", "ssh"))
        return {"service_on": params["host_ip"]}

    def _op_add_honey_credentials(self, params: dict) -> dict:
        # Composite — port of openstack_actuators.AddHoneyCredentials.getAnsibleActions. The harness
        # orchestrator resolved honey_user + password (Faker lives with the Perry engine, not on the box)
        # and did the in-memory decoy-user bookkeeping; the box runs the resulting playbooks in order:
        # real -> create the user (+ optional fake data) + per-cred-user ssh keys; fake -> per-cred-user
        # ssh config only.
        honey_ip = params["honey_host_ip"]
        cred_ip = params["credential_host_ip"]
        cred_users = params.get("credential_users") or []
        honey_user = params["honey_user"]
        if params.get("real"):
            self._executor.create_user(honey_ip, honey_user, params["password"])
            if params.get("fakeData"):
                self._executor.add_fake_data(honey_ip, honey_user, params.get("file_name", "~/decoy.json"),
                                             params.get("file_content", "data.json"))
            for cu in cred_users:
                self._executor.setup_server_ssh_keys(cred_ip, cu, honey_ip, honey_user)
        else:
            for cu in cred_users:
                self._executor.add_to_ssh_config(cred_ip, cu, honey_ip, honey_user)
        return {"honey_user": honey_user, "on": honey_ip, "creds_from": len(cred_users)}


class Executor:
    """The operations the agent can perform on the environment from the box. Separated so the agent's
    auth/dispatch is testable with a stub."""

    def block_ip(self, target_ips: list[str], ip_to_block: str, port: int) -> None:
        raise NotImplementedError

    def configure_decoy(self, host_ip: str, honey_ssh: bool) -> None:
        raise NotImplementedError

    def add_fake_data(self, host_ip: str, host_user: str, dst_path: str, file_content: str) -> None:
        raise NotImplementedError

    def create_user(self, host_ip: str, user: str, password: str, group: str = "admin") -> None:
        raise NotImplementedError

    def setup_server_ssh_keys(self, from_host_ip: str, from_user: str, to_host_ip: str, to_user: str) -> None:
        raise NotImplementedError

    def add_to_ssh_config(self, host_ip: str, host_user: str, follower: str, follower_user: str) -> None:
        raise NotImplementedError

    def start_honey_service(self, host_ip: str, port_no, service: str) -> None:
        raise NotImplementedError


class AnsibleExecutor(Executor):
    """SELF-CONTAINED host-action executor: runs the shipped playbook YAMLs directly via ansible_runner,
    importing NONE of Perry's `defender`/`environment`/`ansible.*` Python packages. That matters because
    the defender box is Ubuntu 20.04 / py3.8, while the Perry codebase needs py3.10+ — but a host action
    is just an ansible playbook (block_ip.yml = iptables over SSH), so the box needs only ansible-core +
    the YAML + an inventory, all py3.8-fine. The box reaches victims DIRECTLY on its subnet (no bastion),
    so the inventory is a flat key+IP list.

    `ansible_dir` is the shipped Perry `ansible/` tree (used as ansible_runner's private_data_dir, so
    playbooks are addressed relative to it, exactly like Perry's own AnsibleRunner does)."""

    def __init__(self, *, ssh_key_path: str, ansible_dir: str, log_dir: str,
                 es_address: Optional[str] = None, es_index: str = "sysflow",
                 es_user: str = "elastic", es_password: str = ""):
        self._key = ssh_key_path
        self._ansible_dir = ansible_dir
        self._log_dir = log_dir
        # Where a decoy's SysFlow exports telemetry — the defender box's ES, reachable from the decoy at
        # the box's in-env address (prepare_box_agent sets this to http://<box_ip>:9200).
        self._es_address = es_address
        self._es_index = es_index
        self._es_user = es_user
        self._es_password = es_password

    def _run_playbook(self, playbook_rel: str, extravars: dict, target_ips: list[str]) -> None:
        import ansible_runner
        inv = {"all": {
            "hosts": {ip: {"ansible_host": ip} for ip in target_ips},
            "vars": {
                "ansible_user": "root",
                "ansible_ssh_private_key_file": self._key,
                "ansible_ssh_common_args": "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
                "ansible_python_interpreter": "auto_silent",
            },
        }}
        r = ansible_runner.run(
            private_data_dir=self._ansible_dir, playbook=playbook_rel, inventory=inv, extravars=extravars,
            envvars={"ANSIBLE_HOST_KEY_CHECKING": "False", "PYTHONPATH": ""},
        )
        if r.status != "successful":
            raise RuntimeError(f"ansible {playbook_rel} -> {r.status} (rc={r.rc})")

    def block_ip(self, target_ips: list[str], ip_to_block: str, port: int) -> None:
        self._run_playbook("defender/capabilities/block_ip.yml",
                           {"hosts": target_ips, "ip_to_block": ip_to_block, "port_to_block": port},
                           target_ips)

    # -- Perry host actions (ports of the removed openstack_actuators + AnsiblePlaybook wrappers; the
    #    playbook paths + variable names are recovered from git so actuation matches the proven behavior) --
    def add_fake_data(self, host_ip: str, host_user: str, dst_path: str, file_content: str) -> None:
        # AddData wrapper: dst_path=path, src_path=file_content (a file resolved in the shipped ansible/ tree).
        self._run_playbook("goals/data/addData.yml",
                           {"host": host_ip, "host_user": host_user, "dst_path": dst_path, "src_path": file_content},
                           [host_ip])

    def create_user(self, host_ip: str, user: str, password: str, group: str = "admin") -> None:
        self._run_playbook("common/createUser/createUser.yml",
                           {"host": host_ip, "user": user, "password": password, "group": group},
                           [host_ip])

    def setup_server_ssh_keys(self, from_host_ip: str, from_user: str, to_host_ip: str, to_user: str) -> None:
        # cross-host: generates a key on from_host + authorizes it on to_host — both are play targets.
        self._run_playbook("deployment_instance/setup_server_ssh_keys/setup_ssh_keys.yml",
                           {"from_host_ip": from_host_ip, "from_user": from_user,
                            "to_host_ip": to_host_ip, "to_user": to_user},
                           [from_host_ip, to_host_ip])

    def add_to_ssh_config(self, host_ip: str, host_user: str, follower: str, follower_user: str) -> None:
        self._run_playbook("deployment_instance/setup_server_ssh_keys/add_to_ssh_config.yml",
                           {"host": host_ip, "host_user": host_user, "follower": follower, "follower_user": follower_user},
                           [host_ip])

    def start_honey_service(self, host_ip: str, port_no, service: str) -> None:
        # The box ES runs plain HTTP (security disabled), so no api key — mirrors prepare_box_es/box ES setup.
        self._run_playbook("defender/deploy_honey_service.yml",
                           {"host": host_ip, "port_no": port_no, "service": service,
                            "elasticsearch_server": self._es_address or "", "elasticsearch_api_key": ""},
                           [host_ip])

    def _write_sysflow_pipeline(self) -> None:
        """Port of InstallSysFlow's pipeline-gen (plain json, py3.8): read the shipped template, point the
        exporter at the box's ES, write pipeline.local.json alongside it (where the sysflow playbook
        copies it from)."""
        import os
        base = os.path.join(self._ansible_dir, "defender", "sysflow")
        with open(os.path.join(base, "pipeline_template.local.json")) as f:
            pipeline = json.load(f)
        for proc in pipeline.get("pipeline", []):
            if proc.get("processor") == "exporter":
                if self._es_address:
                    proc["es.addresses"] = self._es_address
                proc["es.username"] = self._es_user
                proc["es.password"] = self._es_password
                proc["es.index"] = self._es_index
        with open(os.path.join(base, "pipeline.local.json"), "w") as f:
            json.dump(pipeline, f)

    def configure_decoy(self, host_ip: str, honey_ssh: bool) -> None:
        """Self-contained decoy setup: confirm the host is up, write the SysFlow pipeline (exporting to the
        box ES), and run the sysflow install playbook — all via shipped YAMLs, no Perry Python. honey_ssh
        is deferred (DeployHoneyService needs its own playbook + es wiring)."""
        self._run_playbook("deployment_instance/check_if_host_up/check_if_host_up.yml",
                           {"host": host_ip}, [host_ip])
        self._write_sysflow_pipeline()
        self._run_playbook("defender/sysflow/configure_and_start_sysflow.yml", {"host": host_ip}, [host_ip])
        if honey_ssh:
            # DeployHoneyService is a further playbook + es wiring — follow-up; the decoy's core value
            # (a SysFlow-monitored host) is already set up above, so don't fail the action on it.
            pass


def build_http_server(agent: BoxAgent, host: str, port: int):
    """A stdlib http.server bound to (host, port). POST /action -> agent.handle; GET /health -> ok."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send(200, {"ok": True})
            else:
                self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/action":
                self._send(404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"ok": False, "error": "invalid JSON"})
                return
            res = agent.handle(payload)
            status = res.pop("status", 200)
            self._send(status, res)

        def log_message(self, *args):  # silence default stderr spam
            return

    return ThreadingHTTPServer((host, port), _Handler)


def main(argv=None) -> None:
    """Entry point on the box, run STANDALONE (`python /root/box_agent/agent.py --config <path>`, NOT
    `-m defender.box_agent.agent` — that would import the py3.10+ `defender` package and crash on the
    box's py3.8). This module is pure stdlib + ansible_runner; no Perry Python is imported. The config
    JSON (written by the deploy step) carries: token, host, port, ssh_key_path, ansible_dir (the shipped
    `ansible/` YAML tree), log_dir."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args(argv)
    with open(args.config) as f:
        cfg = json.load(f)

    executor = AnsibleExecutor(
        ssh_key_path=cfg["ssh_key_path"], ansible_dir=cfg["ansible_dir"], log_dir=cfg["log_dir"],
        es_address=cfg.get("es_address"), es_index=cfg.get("es_index", "sysflow"),
        es_password=cfg.get("es_password", ""),
    )
    agent = BoxAgent(cfg["token"], executor)
    server = build_http_server(agent, cfg.get("host", "0.0.0.0"), int(cfg["port"]))
    print(f"[box-agent] listening on {cfg.get('host', '0.0.0.0')}:{cfg['port']}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
