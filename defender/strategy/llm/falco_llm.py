from concurrent.futures import ThreadPoolExecutor
from defender.capabilities import RestoreServer
from defender.telemetry.events import SuspiciousHost
from defender.strategy import Strategy
from defender.agents.sysflow.sysflow_agent import SysFlowAgent
from utility.logging import log_event


class FalcoLLM(Strategy):
    _executor: ThreadPoolExecutor = ThreadPoolExecutor(
        max_workers=8, thread_name_prefix="falco-llm"
    )

    def initialize(self):
        log_event("FalcoLLM", "Initializing FalcoLLM strategy")
        self.telemetry_service.subscribe(SuspiciousHost, self._handle_suspicious_host)

    # Subscriber callback: queue work and return immediately.
    def _handle_suspicious_host(self, event: SuspiciousHost):
        log_event("FalcoLLM", f"Suspicious host detected: {event.host_name}")
        FalcoLLM._executor.submit(self._investigate_host, event)
        log_event("FalcoLLM", f"Started investigating host: {event.host_name}")

    def _investigate_host(self, event: SuspiciousHost):
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
            # This strategy restores only on confirmed malware and never reads c2c_ip.
            identify_c2=False,
            sysflow_index=self.telemetry_service.telemetry_analysis.sysflow_index,
        )
        report = sysflow_agent.run()

        log_event(
            "FalcoLLM",
            f"LLM conversation: {sysflow_agent.llm_agent.conversation_to_string()}",
        )

        if not report or not report.malware_confirmed:
            return

        log_event("FalcoLLM", f"LLM report: {report}; restoring {event.host_name}")
        host = self.network.get_host_by_name(event.host_name)
        if host:
            self.orchestrator.run([RestoreServer(host.ip)])
        else:
            log_event("FalcoLLM", f"Host {event.host_name} not found")
