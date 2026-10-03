from defender.telemetry.events import (
    SuspiciousHost,
)
from defender.strategy import Strategy
from utility.logging import log_event


class FalcoTest(Strategy):
    def initialize(self):
        log_event("FalcoTest", "Initializing FalcoTest strategy")

        self.telemetry_service.subscribe(SuspiciousHost, self.handle_suspicious_host)

    def handle_suspicious_host(self, event: SuspiciousHost):
        log_event("FalcoTest", f"Suspicious host detected: {event.host_name}")

    def run(self):
        pass
