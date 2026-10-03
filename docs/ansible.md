# Ansible

Perry executes most of its work on the range through Ansible — installing sensors, deploying decoys,
planting credentials, and (for range setup) injecting vulnerabilities. Everything is under `ansible/`.

## Runner

- **`AnsiblePlaybook.py`** — a thin `{name, params}` wrapper. Per-task `.py` modules subclass it to pair a
  specific `.yml` with typed parameters (e.g. `DeployHoneyService`, `InstallSysFlow`, `SetupServerSSHKeys`).
- **`AnsibleRunner.py`** — the real runner for the OpenStack range. Runs playbooks through a bastion, with
  retries (`run_playbook`) and a production parallel path (`run_playbooks_parallel` /
  `_run_playbook_isolated`) built on a pre-warmed shared-bastion SSH `ControlMaster`. It carries the
  bastion / `PYTHONPATH`-shadowing / `MaxStartups` workarounds mirrored from MHBench — don't strip those;
  they're why parallel deploys over a shared bastion don't wedge.
- `ansible_local_runner.py` / `ansible_docker_runner.py` — simpler runners for local/dev use.

Actuators (see [responses.md](responses.md)) build `AnsiblePlaybook` subclasses and hand them to the runner.

## Playbook categories

| Directory | What it holds |
|-----------|---------------|
| `defender/` | The defensive capabilities: `falco/` (install Falco), `sysflow/` (configure + start SysFlow — **MHBench bakes SysFlow into the image; this only configures/starts it**), `capabilities/` (`SetupFakeCredential`, `block_ip`), honey-service playbooks. |
| `deployment_instance/` | Host bring-up: `check_if_host_up/`, `install_base_packages/`, `setup_server_ssh_keys/` (keys are **generated on-host**, not shipped). |
| `vulnerabilities/` | Intentionally-vulnerable setups that seed the range (Struts, vsftpd backdoor, weak passwords, Equifax config, netcat shell, and a `privledge_escalation/` family). The PE vulns need `sudo` `.deb`s you supply — see that dir's README. |
| `enterprise/` | Active Directory / Samba / Kerberos / SSSD + user/group provisioning. |
| `common/` | Reusable primitives (reboot, changePassword, runCommand, serviceAction, installPackage, createUser, cronJob, addSSHKey, …). |
| `goals/` | Decoy data (`data/AddData.py`, `data.json`, `decoy.json`) used by `AddFakeData` / `AddHoneyCredentials`. |
| `caldera/` | Install Caldera attacker/defender (legacy integration). |
| `configs/`, `inventory/`, `dev/`, `tests/` | ansible.cfg variants, inventories (openstack/docker/gcp), dev inventory, and test scripts. |

## Notes for open-source users

- **SysFlow** `.deb`s are **not** vendored — the baked range image provides SysFlow; this repo only
  configures and starts it.
- **Vulnerable `sudo` `.deb`s** are **not** shipped; place them per
  [`ansible/vulnerabilities/privledge_escalation/README.md`](../ansible/vulnerabilities/privledge_escalation/README.md).
  `*.deb` is gitignored.
