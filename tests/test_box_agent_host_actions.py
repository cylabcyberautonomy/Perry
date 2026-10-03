import os
from unittest.mock import MagicMock
from defender.box_agent.agent import BoxAgent
from defender.orchestrator.RemoteEnvOrchestrator import RemoteEnvOrchestrator

# ---------- box agent dispatch ----------
def test_box_agent():
    ex = MagicMock()
    agent = BoxAgent("tok", ex)
    def call(t, p): return agent.handle({"token": "tok", "action": {"type": t, "params": p}})

    r = call("AddFakeData", {"host_ip": "10.0.0.5", "host_users": ["alice"], "path": "~/",
                             "file_name": "secret.txt", "file_content": "loot.json"})
    assert r["ok"], r
    ex.add_fake_data.assert_called_once_with("10.0.0.5", "alice", os.path.join("~/", "secret.txt"), "loot.json")
    print("box agent AddFakeData OK")

    ex.reset_mock()
    r = call("AddHoneyCredentials", {"honey_host_ip": "10.0.0.9", "credential_host_ip": "10.0.0.5",
             "credential_users": ["bob", "carol"], "honey_user": "trap", "password": "pw",
             "real": True, "fakeData": True, "file_name": "~/creds", "file_content": "x"})
    assert r["ok"], r
    ex.create_user.assert_called_once_with("10.0.0.9", "trap", "pw")
    assert ex.setup_server_ssh_keys.call_count == 2
    ex.add_fake_data.assert_called_once_with("10.0.0.9", "trap", "~/creds", "x")
    print("box agent AddHoneyCredentials(real) OK")

    ex.reset_mock()
    r = call("AddHoneyCredentials", {"honey_host_ip": "10.0.0.9", "credential_host_ip": "10.0.0.5",
             "credential_users": ["bob", "carol"], "honey_user": "trap", "password": "pw", "real": False})
    assert r["ok"] and ex.add_to_ssh_config.call_count == 2 and not ex.create_user.called
    print("box agent AddHoneyCredentials(fake) OK")

    ex.reset_mock()
    r = call("StartHoneyService", {"host_ip": "10.0.0.7", "port_no": "8000", "service": "ssh"})
    assert r["ok"]; ex.start_honey_service.assert_called_once_with("10.0.0.7", "8000", "ssh")
    print("box agent StartHoneyService OK")

    r = call("Nonsense", {}); assert not r["ok"] and r["status"] == 400
    print("box agent unsupported -> 400 OK")

# ---------- orchestrator _host: Host -> flat params ----------
class Host:
    def __init__(self, ip, users=None): self.ip = ip; self.users = users or []
    def add_user(self, u, is_decoy=False): self.users.append(u)
class AddFakeData:
    def __init__(self): self.host = Host("10.0.0.5", ["alice"]); self.path = "~/"; self.file_name = "s.txt"; self.file_content = "loot"; self.user = None
class AddHoneyCredentials:
    def __init__(self, real): self.honey_host = Host("10.0.0.9"); self.credential_host = Host("10.0.0.5", ["bob", "carol"]); self.real = real; self.fakeData = True; self.honey_user = "trap"; self.file_name = "~/c"; self.file_content = "x"; self.number = 1
class StartHoneyService:
    def __init__(self): self.host = Host("10.0.0.7"); self.port_no = "8000"; self.service = "ssh"

def test_orchestrator_host():
    o = RemoteEnvOrchestrator(experiment_name="t", network=MagicMock(), action_logger=MagicMock(),
                              box_agent_host="127.0.0.1", box_agent_token="z")
    o._box_request = MagicMock(return_value={"ok": True})
    o._host(AddFakeData(), "AddFakeData")
    p = o._box_request.call_args[0][1]
    assert p["host_ip"] == "10.0.0.5" and p["host_users"] == ["alice"] and p["file_content"] == "loot", p
    print("orch AddFakeData -> flat params OK:", p)

    o._host(AddHoneyCredentials(real=True), "AddHoneyCredentials")
    p = o._box_request.call_args[0][1]
    assert p["honey_host_ip"] == "10.0.0.9" and p["credential_host_ip"] == "10.0.0.5"
    assert p["credential_users"] == ["bob", "carol"] and p["honey_user"] == "trap" and p["password"] and p["real"] is True, p
    print("orch AddHoneyCredentials -> resolved+flat OK (honey_user=%s pw=***)" % p["honey_user"])

    o._host(StartHoneyService(), "StartHoneyService")
    p = o._box_request.call_args[0][1]
    assert p["host_ip"] == "10.0.0.7" and p["port_no"] == "8000", p
    print("orch StartHoneyService OK")

test_box_agent(); test_orchestrator_host(); print("\nALL BOX-AGENT HANDLER TESTS PASSED")
