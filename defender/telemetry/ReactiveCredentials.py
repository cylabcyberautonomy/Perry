from .TelemetryAnalysis import TelemetryAnalysis

from .events import Event, DecoyHostInteraction, DecoyCredentialUsed

from utility.logging import PerryLogger, log_event

logger = PerryLogger.get_logger()


class ReactiveCredentials(TelemetryAnalysis):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sources already reported as suppressed, so the defender logs each one only once.
        self._suppressed_sources: set = set()

    def _decoy_users_at(self, ip: str) -> list[str]:
        """Honey usernames planted to reach the decoy at `ip`, or an empty list if `ip` is not a decoy or has no honey users yet."""
        for decoy in self.network.get_all_decoys():
            if decoy.ip == ip:
                return list(decoy.decoy_users)
        return []

    def _is_environment_source(self, ip: str | None) -> bool:
        """True only if `ip` belongs to a host or decoy in this experiment's network."""
        if not ip:
            return False
        for host in self.network.get_all_hosts():
            if host.ip == ip:
                return True
        for decoy in self.network.get_all_decoys():
            if decoy.ip == ip:
                return True
        return False

    def process_low_level_events(self, new_telemetry: list[dict]) -> list[Event]:
        high_level_events = []

        for alert in new_telemetry:
            alert_data = alert["_source"]

            if alert["_index"] != self.sysflow_index:
                continue

            event = alert_data.get("event") or {}
            category = event.get("category")
            host_ip = (alert_data.get("host") or {}).get("ip")
            proc = alert_data.get("process") or {}

            if category == "process":
                # Decoy-side login: a shell whose parent is sshd on a decoy is the attacker on the honey credential.
                if host_ip and self.network.is_ip_decoy(host_ip):
                    parent_name = (proc.get("parent") or {}).get("name") or ""
                    if parent_name == "sshd":
                        users = self._decoy_users_at(host_ip) or self.network.get_all_decoy_users()
                        for decoy_user in users:
                            log_event(
                                "ReactiveCredentials",
                                f"Honey credential used: login on decoy {host_ip} "
                                f"(user {decoy_user})",
                            )
                            high_level_events.append(
                                DecoyCredentialUsed(host_ip, decoy_user)
                            )

                # Source-side rule: an ssh client naming a honey user, only from an instrumented host.
                if proc.get("name") == "ssh":
                    cmd = proc.get("command_line") or ""
                    for decoy_user in self.network.get_all_decoy_users():
                        if decoy_user and decoy_user in cmd:
                            high_level_events.append(
                                DecoyCredentialUsed(host_ip, decoy_user)
                            )

            elif category == "network":
                dest = alert_data.get("destination") or {}
                dest_ip = dest.get("ip")
                dest_port = dest.get("port")
                src_ip = (alert_data.get("source") or {}).get("ip")
                cmd_ln = proc.get("command_line") or ""

                # Any SSH connection to a decoy is a decoy interaction. The source must be a real host, not defender provisioning traffic.
                attacker_side = self._is_environment_source(src_ip)
                if not attacker_side and src_ip not in self._suppressed_sources:
                    self._suppressed_sources.add(src_ip)
                    log_event(
                        "ReactiveCredentials",
                        f"Ignoring decoy traffic from {src_ip}: not a host in this "
                        f"experiment's network (defender/management traffic)",
                    )

                if (
                    attacker_side
                    and dest_ip
                    and self.network.is_ip_decoy(dest_ip)
                    and dest_port == 22
                ):
                    log_event(
                        "ReactiveCredentials",
                        f"Decoy interaction: SSH to decoy {dest_ip} from {src_ip}",
                    )
                    high_level_events.append(DecoyHostInteraction(src_ip, dest_ip))

                # Netcat shell rule (decoy on 4444).
                if attacker_side and dest_ip and self.network.is_ip_decoy(dest_ip):
                    if dest_port == 4444 and "/usr/bin/ncat --no-shutdown -i" in cmd_ln:
                        high_level_events.append(DecoyHostInteraction(src_ip, dest_ip))

                # Curl-to-decoy rule (decoy on 8888).
                if attacker_side and host_ip and self.network.is_ip_decoy(host_ip):
                    if dest_port == 8888 and "/usr/bin/curl" in cmd_ln:
                        high_level_events.append(DecoyHostInteraction(src_ip, dest_ip))

        return high_level_events
