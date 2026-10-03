from elasticsearch import Elasticsearch
from environment.network import Network
from defender.telemetry.TelemetryAnalysis import TelemetryAnalysis
from defender.telemetry.index_names import FALCO_BASE, SYSFLOW_BASE
from defender.telemetry.types.falco_alert import FalcoAlert
from defender.telemetry.events import Event, SuspiciousHost, FalcoEvent

from utility.logging import log_event


class FalcoAgressiveAnalysis(TelemetryAnalysis):
    def __init__(
        self,
        elasticsearch_conn: Elasticsearch,
        network: Network,
        falco_index: str = FALCO_BASE,
        sysflow_index: str = SYSFLOW_BASE,
    ):
        super().__init__(elasticsearch_conn, network, falco_index, sysflow_index)

        self.host_alert_counts: dict[str, int] = {}
        self.hosts_triggered_alert: set[str] = set()
        self.count_threshold = 1

    def process_low_level_events(self, new_telemetry: list[dict]) -> list[Event]:
        high_level_events = []

        for alert in new_telemetry:
            if alert["_index"] != self.falco_index:
                continue
            log_event("FalcoAgressiveAnalysis", f"Processing new falco alert")
            alert_data = FalcoAlert(**alert["_source"])
            self.process_host_alert_counts(alert_data)
            high_level_events.append(FalcoEvent(host_name=alert_data.hostname))

            log_event(
                "FalcoAgressiveAnalysis", f"Host alert counts: {self.host_alert_counts}"
            )

        suspicious_hosts = self.check_for_suspicious_host()
        high_level_events.extend(suspicious_hosts)

        return high_level_events

    def process_host_alert_counts(self, alert_data: FalcoAlert):
        log_event(
            "FalcoAgressiveAnalysis",
            f"Processing alert for host: {alert_data.hostname}, rule: {alert_data.rule}",
        )

        if alert_data.hostname not in self.host_alert_counts:
            self.host_alert_counts[alert_data.hostname] = 0

        self.host_alert_counts[alert_data.hostname] += 1

    def check_for_suspicious_host(self) -> list[SuspiciousHost]:
        suspicious_hosts = []
        for host, alert_count in self.host_alert_counts.items():
            if (
                alert_count > self.count_threshold
                and host not in self.hosts_triggered_alert
            ):
                suspicious_hosts.append(SuspiciousHost(host_name=host))
                self.hosts_triggered_alert.add(host)

        return suspicious_hosts
