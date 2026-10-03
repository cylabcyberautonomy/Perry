# Responses (actions)

A strategy responds by building **capability** objects and handing them to the **orchestrator**, which runs
the matching **actuator** against the range. Two layers:

- `defender/capabilities/` — plain parameter-holder dataclasses: the *what*.
- `defender/orchestrator/openstack_actuators/` — the executors (OpenStack SDK + Ansible): the *how*.

Strategies never touch OpenStack/Ansible directly — they emit capabilities.

## The orchestrator

`OpenstackOrchestrator` (`orchestrator/OpenstackOrchestrator.py`) builds an actuator table keyed by
capability class name and tracks `action_counts`. `run(actions)`:

- a batch that is **all `DeployDecoy`** goes through `actuate_batch` (parallel deploy over the shared
  bastion), and
- everything else is dispatched per action to its actuator's `actuate()`.

Each executed action is logged (structlog) and counted.

## Capability → actuator catalog

| Capability (`capabilities/`) | Parameters | Actuator does |
|------------------------------|------------|---------------|
| `DeployDecoy` | `subnet`, `host_name`, `apacheVulnerability`, `honeySSHService` | Boots a decoy from the MHBench-baked Glance image, waits for it, installs/starts SysFlow, optionally a honey SSH service. Supports parallel batch deploy. |
| `RestoreServer` | `host_ip` | Rebuilds (nova rebuild) a compromised host. **Guarded** — see below. |
| `AddHoneyCredentials` | `credential_host`, `honey_host`, `number`, `real`, `fakeData`, `honey_user`, `file_name`, `file_content` | Generates a Faker honey user, creates it, and plants SSH keys/config from a real host to a decoy. (`actuateMany` for batches.) Note the capability prefixes `file_name` with `~/`. |
| `AddFakeData` | `host`, `file_name`, `user`, `path`, `file_content` | Writes decoy files on a host. |
| `BlockIP` | `ip_to_block`, `port` | Blocks a C2 IP (used by `FalcoLLMC2Block`). |
| `StartHoneyService` | `host`, `port_no="8000"`, `service="ssh"` | Stands up a fake SSH listener. |
| `ShutdownServer` | `host_ip` | Shuts a host down (no Ansible). |

## Safety guards on `RestoreServer`

`RestoreServer` can rebuild VMs, so it is deliberately conservative
(`openstack_actuators/RestoreServer.py`):

- **Allowlist (primary, fails safe):** `_is_defendable_host()` — only hosts the defender legitimately owns
  are restorable; anything it can't positively classify is refused.
- **Denylist (secondary):** `sensitive_subnets` (management/attacker/relay subnets) are never restored.

Both exist because of documented incidents (restoring the attacker's foothold, self-triggered restores from
the defender's own traffic). **Don't weaken them** without reading the rationale in the file.

## Adding a response action

1. Add a parameter-holder dataclass to `capabilities/` (subclass `Action`).
2. Add an executor to `orchestrator/openstack_actuators/` (subclass `OpenstackActuator`, implement
   `actuate(action)`), using the OpenStack SDK and/or `AnsibleRunner` (see [ansible.md](ansible.md)).
3. Register it in `OpenstackOrchestrator`'s actuator table (keyed by the capability class name).
4. Have a strategy build and dispatch it (see [strategies.md](strategies.md)).
