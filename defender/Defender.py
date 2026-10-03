from .orchestrator import Orchestrator
from .arsenal import Arsenal
from .strategy import Strategy
from .telemetry.telemetry_service import TelemetryService

from environment.network import Network

from .telemetry.telemetry_service import TelemetryService


class Defender:
    def __init__(
        self,
        arsenal: Arsenal,
        strategy: Strategy,
        telemetry_service: TelemetryService,
        orchestrator: Orchestrator,
        network: Network,
    ):
        self.metrics = {}
        self.arsenal = arsenal
        self.strategy = strategy
        self.telemetry_service = telemetry_service
        self.orchestrator = orchestrator
        self.network = network

    def prepare(self):
        """Run external arming before the scenario loop for ARMS_IN_SETUP strategies."""
        if self.strategy.ARMS_IN_SETUP:
            self.strategy.initialize()

    def start(self, prepared: bool = False):
        """Initialize the strategy and start telemetry inside the scenario-loop process."""
        if self.strategy.ARMS_IN_SETUP:
            if not prepared:
                self.strategy.initialize()
        else:
            self.strategy.initialize()
        self.telemetry_service.telemetry_analysis.begin_monitoring()

    def run(self):
        self.telemetry_service.process_telemetry()
        self.strategy.run()
