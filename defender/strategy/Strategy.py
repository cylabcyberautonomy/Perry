from defender.arsenal import CountArsenal
from environment.network import Network
from defender.orchestrator import Orchestrator
from utility.logging import get_logger
from defender.telemetry.telemetry_service import TelemetryService

from abc import ABC, abstractmethod
from typing import Optional


class Strategy(ABC):
    # True if initialize() is pure external arming that runs in the setup phase.
    ARMS_IN_SETUP: bool = False

    def __init__(
        self,
        arsenal: CountArsenal,
        network: Network,
        orchestrator: Orchestrator,
        telemetry_service: TelemetryService,
        llm_model: Optional[str] = None,
    ):
        self.arsenal = arsenal
        self.network = network
        self.orchestrator = orchestrator
        self.telemetry_service = telemetry_service
        self.logger = get_logger()
        self.llm_model = llm_model

    @abstractmethod
    def initialize(self):
        pass

    def run(self):
        return

    def _honeycred_deploy_hosts(self, count: int) -> list:
        """Entry-segment hosts that receive honey credentials."""
        subnets = [
            s for s in self.network.subnets if not getattr(s, "attacker", False)
        ] or self.network.subnets
        if not subnets:
            return []
        entry = next((s for s in subnets if getattr(s, "entry", False)), subnets[0])
        if not entry.hosts:
            return []
        return [entry.hosts[i % len(entry.hosts)] for i in range(count)]

    def _defended_host_count(self) -> int:
        """Count real hosts across the defended (non-attacker) subnets."""
        subnets = [
            s for s in self.network.subnets if not getattr(s, "attacker", False)
        ] or self.network.subnets
        return sum(len(s.hosts) for s in subnets)

    def _default_decoy_count(self) -> int:
        """Default DeployDecoy count: a third of the defended hosts, at least 1, or 0 if none exist."""
        hosts = self._defended_host_count()
        return max(1, round(hosts / 3)) if hosts else 0
