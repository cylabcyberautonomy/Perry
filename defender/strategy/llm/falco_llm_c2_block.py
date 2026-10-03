from defender.capabilities import (
    BlockIP,
)

from defender.telemetry.events import (
    SuspiciousHost,
)
from defender.strategy import Strategy
from defender.agents.sysflow.sysflow_agent import SysFlowAgent
from utility.logging import log_event
from concurrent.futures import ThreadPoolExecutor
import traceback


class FalcoLLMC2Block(Strategy):
    _executor: ThreadPoolExecutor = ThreadPoolExecutor(
        max_workers=8, thread_name_prefix="falco-llm-c2-block"
    )

    def initialize(self):
        log_event("FalcoLLMC2Block", "Initializing FalcoLLMC2Block strategy")
        self.telemetry_service.subscribe(SuspiciousHost, self._handle_suspicious_host)

    # Subscriber callback: queue work and return immediately.
    def _handle_suspicious_host(self, event: SuspiciousHost):
        log_event("FalcoLLMC2Block", f"Suspicious host detected: {event.host_name}")
        future = FalcoLLMC2Block._executor.submit(self._investigate_host, event)
        future.add_done_callback(lambda f: self._handle_investigation_result(f, event))
        log_event("FalcoLLMC2Block", f"Started investigating host: {event.host_name}")

    def _handle_investigation_result(self, future, event: SuspiciousHost):
        """Handle the result or exception from the investigation thread."""
        try:
            result = future.result()
            log_event(
                "FalcoLLMC2Block",
                f"Investigation completed successfully for {event.host_name}",
            )
        except Exception as e:
            log_event(
                "FalcoLLMC2Block",
                f"Investigation failed for {event.host_name}: {str(e)}",
            )
            log_event(
                "FalcoLLMC2Block",
                f"Investigation error traceback: {traceback.format_exc()}",
            )

    def _investigate_host(self, event: SuspiciousHost):
        """Run the SysFlow agent investigation in a background thread."""
        host = self.network.get_host_by_name(event.host_name)
        if host is None:
            log_event(self.__class__.__name__, f"Host {event.host_name} not found")
            return
        host_ip = host.ip
        if self.llm_model is None:
            raise ValueError("llm_model is required for this strategy")

        sysflow_agent = SysFlowAgent(
            self.telemetry_service.telemetry_analysis.elasticsearch_conn,
            host_ip,
            self.llm_model,
            # This strategy blocks the C2 IP, so it needs the model to identify one.
            identify_c2=True,
            sysflow_index=self.telemetry_service.telemetry_analysis.sysflow_index,
        )
        report = sysflow_agent.run()

        llm_conversation = sysflow_agent.llm_agent.conversation_to_string()
        log_event(self.__class__.__name__, f"LLM conversation: {llm_conversation}")

        if report is None:
            log_event(self.__class__.__name__, "No report found")
            return None

        if report.malware_confirmed:
            log_event(self.__class__.__name__, f"LLM report: {report}")
            log_event(self.__class__.__name__, f"Restoring server {event.host_name}")
            host = self.network.get_host_by_name(event.host_name)
            if host is None:
                log_event(self.__class__.__name__, f"Host {event.host_name} not found")
                return

            # Hard-code the port because other things run on the external ip.
            # TODO: Have attacker C2C run inside environment to avoid this problem
            self.orchestrator.run([BlockIP(report.c2c_ip, 8888)])

    def run(self):
        pass
