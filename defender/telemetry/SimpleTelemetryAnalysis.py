from .TelemetryAnalysis import TelemetryAnalysis

from .events import Event, DecoyHostInteraction

from utility.logging import log_event, get_logger

logger = get_logger()


class SimpleTelemetryAnalysis(TelemetryAnalysis):
    def process_low_level_events(self, new_telemetry: list[dict]) -> list[Event]:
        high_level_events = []

        for alert in new_telemetry:
            alert_data = alert["_source"]

            if alert["_index"] == self.sysflow_index:
                if alert_data["event"]["category"] != "network":
                    continue

                cmd_ln = alert_data["process"]["command_line"]
                dest_port = alert_data["destination"]["port"]
                dest_ip = alert_data["destination"]["ip"]

                if "destination" in alert_data and "process" in alert_data:
                    # Netcat shell rule.
                    if self.network.is_ip_decoy(dest_ip):
                        if (
                            dest_port == 4444
                            and "/usr/bin/ncat --no-shutdown -i" in cmd_ln
                        ):
                            # fmt: off
                            log_event("Decoy host interaction", alert_data["source"]["ip"])
                            # fmt: on

                            attacker_on_host_event = DecoyHostInteraction(
                                alert_data["source"]["ip"],
                                alert_data["destination"]["ip"],
                            )
                            high_level_events.append(attacker_on_host_event)

                    if self.network.is_ip_decoy(alert_data["host"]["ip"]):
                        if dest_port == 8888 and "/usr/bin/curl" in cmd_ln:
                                # fmt: off
                                log_event("Decoy host interaction", alert_data["source"]["ip"])
                                # fmt: on
                                attacker_on_host_event = DecoyHostInteraction(
                                    alert_data["source"]["ip"],
                                    alert_data["destination"]["ip"],
                                )
                                high_level_events.append(attacker_on_host_event)

        return high_level_events
