import ansible_runner
import hashlib
import ipaddress
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich import print
import time
from pathlib import Path

# Serializes appends to the shared log from parallel worker threads.
_PARALLEL_LOG_LOCK = threading.Lock()

from .AnsiblePlaybook import AnsiblePlaybook

from contextlib import redirect_stdout
from os import path

from utility.logging import get_logger

logger = get_logger()

# Prepend this venv bin so ansible_runner finds this venv ansible-playbook on PATH.
# Use the parent as given, not resolved, because bin/python3 symlinks to system python.
_venv_bin = str(Path(sys.executable).parent)
if _venv_bin not in os.environ.get("PATH", "").split(os.pathsep):
    os.environ["PATH"] = _venv_bin + os.pathsep + os.environ.get("PATH", "")


class AnsibleRunner:
    def __init__(
        self,
        ssh_key_path,
        management_ip,
        ansible_dir,
        log_path,
        inventory_file=None,
        config_file=None,
    ):
        self.ssh_key_path = ssh_key_path
        self.management_ip = management_ip
        self.ansible_dir = ansible_dir
        self.log_path = log_path
        # 5 retries / 20s backoff: transient SSH blips under multi-VM cluster load.
        self.MAX_RETRIES = 5

        if inventory_file is None:
            self.inventory_file = "inventory.openstack"
        else:
            self.inventory_file = inventory_file

        self.ansible_vars_default = {
            "manage_ip": self.management_ip,
            "ssh_key_path": self.ssh_key_path,
        }
        if config_file is not None:
            self.config_settings = {
                "ansible_config": config_file,
            }
            os.environ["ANSIBLE_CONFIG"] = config_file
        else:
            self.config_settings = {}

    @staticmethod
    def _target_ips(params: dict) -> list[str]:
        """Every literal IP among a playbook's params, in order, deduplicated."""
        found: list[str] = []
        for value in params.values():
            candidates = value if isinstance(value, list) else [value]
            for candidate in candidates:
                try:
                    ipaddress.ip_address(candidate)
                except (ValueError, TypeError):
                    continue
                if candidate not in found:
                    found.append(candidate)
        return found

    def _bastion_inventory(self, hosts) -> dict | None:
        """Build an ansible-runner inventory that reaches `hosts` through the bastion. Return None when no literal IPs."""
        if not hosts:
            return None

        proxy = (
            f"ssh -W %h:%p -i {self.ssh_key_path} "
            "-o BatchMode=yes -o PasswordAuthentication=no "
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            "-o ControlMaster=auto -o ControlPersist=300s "
            f"root@{self.management_ip}"
        )
        return {
            "all": {
                "hosts": {
                    h: {
                        "ansible_host": h,
                        "ansible_port": 22,
                        "ansible_user": "root",
                        "ansible_ssh_private_key_file": self.ssh_key_path,
                        "ansible_ssh_common_args": (
                            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                            "-o ServerAliveInterval=30 -o ServerAliveCountMax=10 "
                            f'-o ProxyCommand="{proxy}"'
                        ),
                    }
                    for h in hosts
                }
            }
        }

    def run_playbook(self, playbook: AnsiblePlaybook):
        print(f"\n")
        print(f"[RUNNING PLAYBOOK]    {playbook.name}")
        print(f"[PLAYBOOK  PARAMS]    {playbook.params}")

        log_path = path.join(self.log_path, "ansible_log.log")

        # Clear PYTHONPATH: this repo's own `ansible/` package would shadow
        # ansible-core for the child. update() cannot delete a key, so override with empty.
        clean_env = {"PYTHONPATH": ""}

        inventory = self._bastion_inventory(self._target_ips(playbook.params))
        run_kwargs = dict(
            private_data_dir=self.ansible_dir,
            playbook=playbook.name,
            cancel_callback=lambda: None,
            envvars=clean_env,
        )
        if inventory is not None:
            run_kwargs["inventory"] = inventory

        ansible_result = None
        for _ in range(self.MAX_RETRIES):
            playbook_full_params = self.ansible_vars_default | playbook.params
            ansible_result = ansible_runner.run(
                extravars=playbook_full_params,
                **run_kwargs,
            )

            if ansible_result.status == "successful":
                break
            else:
                time.sleep(20)

        if ansible_result is not None and isinstance(
            ansible_result, ansible_runner.Runner
        ):
            with open(log_path, "a") as f:
                try:
                    ansible_result.stdout.seek(0)
                    stdout_content = ansible_result.stdout.read()
                    if stdout_content:
                        f.write(stdout_content)
                except Exception as e:
                    f.write(f"Error reading stdout: {e}\n")
                finally:
                    ansible_result.stdout.close()

                try:
                    ansible_result.stderr.seek(0)
                    stderr_content = ansible_result.stderr.read()
                    if stderr_content:
                        f.write(stderr_content)
                except Exception as e:
                    f.write(f"Error reading stderr: {e}\n")
                finally:
                    ansible_result.stderr.close()

        if ansible_result is None or ansible_result.status != "successful":
            raise Exception(f"Playbook {playbook.name} failed")

        return ansible_result

    def run_playbooks(self, playbooks: list[AnsiblePlaybook], run_async=True):
        if run_async:
            self.run_playbooks_async(playbooks)
        else:
            self.run_playbooks_serial(playbooks)

    def run_playbooks_serial(self, playbooks: list[AnsiblePlaybook]):
        for playbook in playbooks:
            self.run_playbook(playbook)

    def run_playbooks_async(self, playbooks: list[AnsiblePlaybook]):
        threads = []
        runners = []
        log_path = path.join(self.log_path, "ansible_log.log")
        with open(log_path, "a") as f:
            with redirect_stdout(f):
                for i in range(0, len(playbooks), 10):
                    for playbook in playbooks[i : i + 10]:
                        playbook_full_params = (
                            self.ansible_vars_default | playbook.params
                        )
                        thread, runner = ansible_runner.run_async(
                            extravars=playbook_full_params,
                            private_data_dir=self.ansible_dir,
                            playbook=playbook.name,
                            quiet=False,
                        )
                        threads.append(thread)
                        runners.append(runner)

                    for thread in threads:
                        thread.join()

                    for runner in runners:
                        if runner.status == "failed":
                            logger.error(f"Playbook failed")
                            logger.error(f"Playbook Output: {runner.stdout}")
                            logger.error(f"Playbook Error: {runner.stderr}")
                            raise Exception(f"Playbook failed")

    def _ssh_ctl_dir(self) -> str:
        """Per-experiment local dir for the shared bastion ControlPath socket, named by a hash to stay under the 108-byte cap."""
        key = hashlib.sha256((self.management_ip or "default").encode()).hexdigest()[:16]
        d = f"/tmp/mhbench-ssh/{key}"
        os.makedirs(d, exist_ok=True)
        return d

    def _bastion_inventory_mux(self, hosts, control_path) -> dict | None:
        """Like _bastion_inventory, but pins a shared ControlPath so concurrent plays reuse one bastion master connection."""
        if not hosts:
            return None
        proxy = (
            f"ssh -W %h:%p -i {self.ssh_key_path} "
            "-o BatchMode=yes -o PasswordAuthentication=no "
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"-o ControlMaster=auto -o ControlPath={control_path} -o ControlPersist=300s "
            f"root@{self.management_ip}"
        )
        return {
            "all": {
                "hosts": {
                    h: {
                        "ansible_host": h,
                        "ansible_port": 22,
                        "ansible_user": "root",
                        "ansible_ssh_private_key_file": self.ssh_key_path,
                        "ansible_ssh_common_args": (
                            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                            "-o ServerAliveInterval=30 -o ServerAliveCountMax=10 "
                            f'-o ProxyCommand="{proxy}"'
                        ),
                    }
                    for h in hosts
                }
            }
        }

    def _prepare_bastion_mux(self, control_path) -> None:
        """Raise the bastion MaxStartups and pre-establish the shared ControlMaster before concurrent plays start. Best-effort."""
        # Raise MaxStartups (stock throttles the burst) and reload sshd. One-off admin op.
        base_bastion = {
            "ansible_host": self.management_ip,
            "ansible_user": "root",
            "ansible_ssh_private_key_file": self.ssh_key_path,
        }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ansible_runner.run(
                    private_data_dir=tmp, host_pattern="bastion", module="raw",
                    module_args=(
                        "sed -i '/^[[:space:]]*MaxStartups/d' /etc/ssh/sshd_config && "
                        "printf 'MaxStartups 200:30:400\\n' >> /etc/ssh/sshd_config && "
                        "(systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || service ssh reload)"
                    ),
                    quiet=True, envvars={"PYTHONPATH": ""},
                    inventory={"all": {"hosts": {"bastion": {
                        **base_bastion,
                        "ansible_ssh_common_args": "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
                    }}}},
                )
        except Exception:
            logger.warning("Bastion MaxStartups raise failed; continuing with stock limit")
        # Pre-warm the shared ControlMaster so the per-host ProxyCommands reuse it.
        try:
            with tempfile.TemporaryDirectory() as tmp:
                warm = ansible_runner.run(
                    private_data_dir=tmp, host_pattern="bastion", module="raw",
                    module_args="true", quiet=True, envvars={"PYTHONPATH": ""},
                    inventory={"all": {"hosts": {"bastion": {
                        **base_bastion,
                        "ansible_ssh_common_args": (
                            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                            f"-o ControlMaster=auto -o ControlPath={control_path} -o ControlPersist=300s"
                        ),
                    }}}},
                )
            if warm.status == "successful":
                logger.info("Bastion ControlMaster pre-warmed at %s", self.management_ip)
            else:
                logger.warning("Bastion ControlMaster pre-warm status=%s; on-demand fallback", warm.status)
        except Exception:
            logger.warning("Bastion ControlMaster pre-warm failed; on-demand fallback")

    def run_playbooks_parallel(self, playbooks: list, max_workers: int = 8) -> None:
        """Run independent playbooks concurrently through the bastion with ControlMaster multiplexing. Use only for plays with no cross-host dependencies."""
        if not playbooks:
            return
        all_ips: list[str] = []
        for pb in playbooks:
            for ip in self._target_ips(pb.params):
                if ip not in all_ips:
                    all_ips.append(ip)
        ctl_dir = self._ssh_ctl_dir()
        control_path = f"{ctl_dir}/bastion-{self.management_ip}"
        inventory = self._bastion_inventory_mux(all_ips, control_path)
        self._prepare_bastion_mux(control_path)

        errors = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self._run_playbook_isolated, pb, inventory, ctl_dir): pb for pb in playbooks}
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc is not None:
                    errors.append((futures[fut], exc))
        if errors:
            raise Exception(
                f"Parallel playbooks failed on {len(errors)}/{len(playbooks)}: "
                + "; ".join(f"{pb.name}: {e}" for pb, e in errors[:5])
            )

    def _run_playbook_isolated(self, playbook, inventory, ssh_ctl_dir) -> None:
        """Run one playbook in its own private_data_dir, thread-safe under the parallel runner. quiet=True plus event_handler avoid the off-thread deadlock."""
        lines: list[str] = []

        def _stream(event: dict) -> bool:
            s = event.get("stdout", "")
            if s:
                lines.append(s)
            return True

        envvars = {
            # Clear PYTHONPATH: this repo's `ansible/` package would shadow ansible-core.
            "PYTHONPATH": "",
            # One reused SSH connection per host, keyed by %C in this experiment ctl dir.
            "ANSIBLE_SSH_ARGS": (
                "-o ControlMaster=auto "
                f"-o ControlPath={ssh_ctl_dir}/%C "
                "-o ControlPersist=60s "
                "-o StrictHostKeyChecking=no "
                "-o UserKnownHostsFile=/dev/null "
                "-o ServerAliveInterval=30 "
                "-o ServerAliveCountMax=10"
            ),
            "ANSIBLE_PIPELINING": "True",
            "ANSIBLE_SSH_RETRIES": "3",
        }

        result = None
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(self.MAX_RETRIES):
                lines.clear()
                params = self.ansible_vars_default | playbook.params
                run_kwargs = dict(
                    private_data_dir=tmp,
                    # private_data_dir is a per-thread tmp, so point project_dir at the
                    # real playbook tree or ansible cannot find the playbook.
                    project_dir=self.ansible_dir,
                    playbook=playbook.name,
                    extravars=params,
                    event_handler=_stream,
                    quiet=True,
                    envvars=envvars,
                )
                if inventory is not None:
                    run_kwargs["inventory"] = inventory
                result = ansible_runner.run(**run_kwargs)
                if result.status == "successful":
                    break
                time.sleep(20)
        with _PARALLEL_LOG_LOCK:
            try:
                with open(path.join(self.log_path, "ansible_log.log"), "a") as f:
                    f.write("".join(lines))
            except Exception:
                pass
        if result is None or result.status != "successful":
            raise Exception(f"Playbook {playbook.name} failed")

    def update_management_ip(self, new_ip):
        self.management_ip = new_ip
        self.ansible_vars_default["manage_ip"] = new_ip
