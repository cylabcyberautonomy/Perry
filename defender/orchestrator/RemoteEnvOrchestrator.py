"""RemoteEnvOrchestrator — the defender acts WITHOUT holding a cloud credential.

Sibling of OpenstackOrchestrator / GCPOrchestrator, but it holds NO ``openstack_conn`` and runs NO
ansible itself. Instead it separates the controller from the effector: the defender's decision loop
runs where the strategy lives, but every ACTION is sent out to be executed elsewhere, by the party that
legitimately can:

  * HOST-level actions (BlockIP, AddFakeData, AddHoneyCredentials, StartHoneyService, and the
    sensor/vulnerability setup of a decoy) -> the BOX AGENT, a daemon on the defender box. It runs
    the ansible from INSIDE the environment
    (box -> victims, over the defender's scoped key), so no host action emanates from the management host.

  * INFRA actions (DeployDecoy's VM create, RestoreServer, ShutdownServer) -> the ENVIRONMENT, over the
    arena's UDS action channel. The environment is the ONLY holder of the cloud credential; the box never
    touches cloud APIs (a cloud credential on an in-environment VM would be an over-broad exposure).

DeployDecoy is the hybrid: create the VM via the environment (which returns a defender-scoped SetupAccess),
then hand the box agent the host-level setup for that new IP.

Transports are stdlib only (no new dependency in the Defense venv): http.client over an AF_UNIX socket for
the env channel, http.client over TCP for the box agent. The box-agent channel carries a per-experiment
bearer token (it is a TCP service inside the environment, reachable from in-env); the env UDS channel does
not (it is unreachable from in-env, so the transport is the boundary).
"""
from __future__ import annotations

import json
import socket
import http.client
from typing import Optional
from urllib.parse import urlparse

from defender.orchestrator.Orchestrator import Orchestrator
from utility.logging import log_event


class _UnixHTTPConnection(http.client.HTTPConnection):
    """http.client over an AF_UNIX socket — lets us POST to the arena env channel (a Unix socket, so no
    in-env VM can reach it) with zero extra dependency."""

    def __init__(self, socket_path: str, timeout: Optional[float] = 30):
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            s.settimeout(self.timeout)
        s.connect(self._socket_path)
        self.sock = s


def _post_json(conn: http.client.HTTPConnection, path: str, body: dict, extra_headers: dict = None) -> dict:
    payload = json.dumps(body)
    headers = {"Content-Type": "application/json", "Content-Length": str(len(payload))}
    if extra_headers:
        headers.update(extra_headers)
    conn.request("POST", path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"ok": False, "error": f"non-JSON response ({resp.status}): {raw[:200]!r}"}
    data.setdefault("status", resp.status)
    return data


# Which concrete actions go where. Keyed by the capability class name (matches OpenstackOrchestrator's
# action.__class__.__name__ dispatch). DeployDecoy is handled specially (hybrid), so it is in neither set.
_INFRA_ACTIONS = {"RestoreServer", "ShutdownServer"}
_HOST_ACTIONS = {"BlockIP", "AddFakeData", "AddHoneyCredentials", "StartHoneyService"}


def _host_ip(host):
    """A host action may carry a Host object or a bare ip string; the box agent needs the ip."""
    return getattr(host, "ip", host)


def _user_names(host) -> list:
    """The user names on a host (Host.users may be User objects or plain strings)."""
    return [getattr(u, "name", u) for u in (getattr(host, "users", None) or [])]


class RemoteEnvOrchestrator(Orchestrator):
    def __init__(
        self,
        *,
        experiment_name: str,
        network,
        action_logger,
        env_socket: Optional[str] = None,
        env_url: Optional[str] = None,
        env_token: Optional[str] = None,
        box_agent_host: str = None,
        box_agent_port: int = 8900,
        box_agent_token: str = "",
        action_counts: Optional[dict] = None,
        timeout: float = 120.0,
    ):
        # No actuators dict / cloud handle: this orchestrator forwards, it does not actuate locally.
        super().__init__(actuators={}, action_counts=action_counts or {})
        self.experiment_name = experiment_name
        self.network = network
        self.action_logger = action_logger
        # Env channel transport: a box-resident (runs_on_box) runner reaches the arena over a TOKEN'd TCP
        # url (via the harness-initiated ssh -R tunnel, box-loopback); a harness-run runner over the UDS.
        self._env_socket = env_socket
        self._env_url = env_url
        self._env_token = env_token
        self._box_host = box_agent_host
        self._box_port = int(box_agent_port)
        self._box_token = box_agent_token
        self._timeout = timeout

    @classmethod
    def from_config(cls, config: dict, *, experiment_name: str, network, action_logger):
        """Build from the defender runner's config dict — the single construction path the three runner
        scripts (llm_soc / deception / prompt_injection) share. env_action_socket is injected by the arena
        when dynamic topology is armed; the box-agent host/port/token come from the deploy wiring (the box
        host falls back to the defender_env_spec box IP)."""
        box = (config.get("defender_env_spec") or {}).get("box") or {}
        return cls(
            experiment_name=experiment_name,
            network=network,
            action_logger=action_logger,
            # box-resident runner: env_action_url + token (TCP tunnel); harness-run: env_action_socket (UDS).
            env_socket=config.get("env_action_socket"),
            env_url=config.get("env_action_url"),
            env_token=config.get("env_action_token"),
            box_agent_host=config.get("box_agent_host") or box.get("ip"),
            box_agent_port=int(config.get("box_agent_port", 8900)),
            box_agent_token=config.get("box_agent_token", ""),
        )

    # -- transports --------------------------------------------------------
    def _env_request(self, action: dict) -> dict:
        """POST one EnvActionRequest to the arena environment channel. action = {kind, name, role, subnet,
        target}. A box-resident (runs_on_box) runner reaches the arena over the TOKEN'd TCP url (env_url,
        box-loopback via the harness-initiated ssh -R tunnel) with the X-Arena-Token header; a harness-run
        runner over the UDS (no token — the socket is the boundary). The arena budget-checks the serving
        window and actuates on its backend."""
        body = {"experiment_name": self.experiment_name, "action": action}
        if self._env_url:
            u = urlparse(self._env_url)
            conn = http.client.HTTPConnection(u.hostname, u.port, timeout=self._timeout)
            try:
                return _post_json(conn, "/environment/action", body,
                                  extra_headers={"X-Arena-Token": self._env_token or ""})
            finally:
                conn.close()
        conn = _UnixHTTPConnection(self._env_socket, timeout=self._timeout)
        try:
            return _post_json(conn, "/environment/action", body)
        finally:
            conn.close()

    def _box_request(self, action_type: str, params: dict) -> dict:
        """POST one host-level action to the box agent (TCP, on the defender box). The agent runs the
        matching ansible playbook locally (box -> victims)."""
        conn = http.client.HTTPConnection(self._box_host, self._box_port, timeout=self._timeout)
        try:
            return _post_json(conn, "/action", {
                "token": self._box_token,
                "action": {"type": action_type, "params": params},
            })
        finally:
            conn.close()

    # -- dispatch ----------------------------------------------------------
    def run(self, actions: list) -> None:
        for action in actions:
            name = type(action).__name__
            self.action_counts[name] = self.action_counts.get(name, 0) + 1
            try:
                if name == "DeployDecoy":
                    self._deploy_decoy(action)
                elif name in _INFRA_ACTIONS:
                    self._infra(action, name)
                elif name in _HOST_ACTIONS:
                    self._host(action, name)
                else:
                    log_event("Unroutable action",
                              f"RemoteEnvOrchestrator has no route for {name}; skipping")
            except Exception as e:  # noqa: BLE001 — a failed action must not crash the defender loop
                log_event("Action failed", f"{name}: {e}")

    # -- per-action routing ------------------------------------------------
    def _infra(self, action, name: str) -> None:
        kind = {"RestoreServer": "RebuildHost", "ShutdownServer": "RemoveHost"}[name]
        log_event(f"{name} -> env", f"{kind} target={action.host_ip}")
        res = self._env_request({"kind": kind, "target": action.host_ip})
        if not res.get("ok"):
            log_event(f"{name} rejected", f"env said: {res.get('error')}")

    def _host(self, action, name: str) -> None:
        # Host actions carry Host objects (host / honey_host / credential_host) that the generic jsonable
        # flatten would DROP, so each is flattened explicitly to the ip + user names the box agent needs.
        # The box runs the playbook; the harness keeps the decision logic that needs the Perry engine (the
        # honey-cred Faker + the in-memory decoy-user bookkeeping) — mirrors sandcat (dumb) vs the planner.
        if name == "BlockIP":
            params = {"ip_to_block": action.ip_to_block, "port": action.port,
                      "target_ips": self.network.get_all_host_ips()}
        elif name == "AddFakeData":
            params = {"host_ip": _host_ip(action.host), "host_users": _user_names(action.host),
                      "path": getattr(action, "path", None), "file_name": getattr(action, "file_name", None),
                      "file_content": getattr(action, "file_content", None)}
        elif name == "StartHoneyService":
            params = {"host_ip": _host_ip(action.host),
                      "port_no": getattr(action, "port_no", "8000"), "service": getattr(action, "service", "ssh")}
        elif name == "AddHoneyCredentials":
            params = self._honey_cred_params(action)
        else:
            params = {k: v for k, v in vars(action).items()
                      if not k.startswith("_") and isinstance(v, (str, int, float, bool, list, dict, type(None)))}
        log_event(f"{name} -> box", f"params={params}")
        res = self._box_request(name, params)
        if not res.get("ok"):
            log_event(f"{name} rejected", f"box agent said: {res.get('error')}")

    def _honey_cred_params(self, action) -> dict:
        """Resolve the composite AddHoneyCredentials harness-side (it needs the Perry engine): pick/fake the
        honey user + password, record the decoy user in the in-memory Network, and flatten honey_host /
        credential_host to the ip + user names the box agent's _op_add_honey_credentials runs the playbooks
        from. Mirrors openstack_actuators.AddHoneyCredentials.getAnsibleActions' decision half."""
        honey_user = getattr(action, "honey_user", None)
        password = ""
        try:
            from faker import Faker
            fake = Faker()
            if not honey_user:
                honey_user = fake.name().replace(" ", "")
            password = fake.password()
        except Exception:  # noqa: BLE001 — Faker is a Perry dep; degrade rather than crash the loop
            honey_user = honey_user or "decoyuser"
            password = password or "Decoy!Passw0rd"
        try:
            action.honey_host.add_user(honey_user, is_decoy=True)
        except Exception:  # noqa: BLE001
            pass
        return {"honey_host_ip": _host_ip(action.honey_host),
                "credential_host_ip": _host_ip(action.credential_host),
                "credential_users": _user_names(action.credential_host),
                "honey_user": honey_user, "password": password,
                "real": bool(getattr(action, "real", False)),
                "fakeData": bool(getattr(action, "fakeData", False)),
                "file_name": getattr(action, "file_name", None),
                "file_content": getattr(action, "file_content", None)}

    def _deploy_decoy(self, action) -> None:
        """Hybrid: create the VM via the environment (returns a defender-scoped SetupAccess), then hand the
        box agent the host-level setup (sensor install + vulnerability + honey SSH) for the new IP."""
        role = "apache_vuln" if getattr(action, "apacheVulnerability", False) else "decoy"
        subnet = getattr(action, "subnet", None)
        subnet_name = getattr(subnet, "name", None)
        log_event("DeployDecoy -> env", f"AddHost name={action.host_name} role={role} subnet={subnet_name}")
        res = self._env_request({"kind": "AddHost", "name": action.host_name,
                                 "role": role, "subnet": subnet_name})
        if not res.get("ok"):
            log_event("DeployDecoy rejected", f"env said: {res.get('error')}")
            return
        ip, access = res.get("ip"), res.get("access")
        log_event("DeployDecoy -> box", f"ConfigureDecoy ip={ip}")
        box_res = self._box_request("ConfigureDecoy", {
            "host_ip": ip,
            "host_name": action.host_name,
            "access": access,  # defender-scoped SetupAccess the box uses to reach the new host
            "apacheVulnerability": bool(getattr(action, "apacheVulnerability", False)),
            "honeySSHService": bool(getattr(action, "honeySSHService", False)),
        })
        if not box_res.get("ok"):
            log_event("DeployDecoy setup failed", f"box agent said: {box_res.get('error')}")
        else:
            # Register the decoy in the defender's Network so later telemetry/actions see it.
            try:
                from environment.network import Host
                if ip and subnet is not None:
                    subnet.add_host(Host(action.host_name, ip), decoy=True)
            except Exception as e:  # noqa: BLE001
                log_event("Decoy registration skipped", str(e))
