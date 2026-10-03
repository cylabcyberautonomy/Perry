from .TelemetryAnalysis import TelemetryAnalysis

from .events import Event


class NoTelemetry(TelemetryAnalysis):
    def __init__(self, elasticsearch_conn, network, falco_index=None, sysflow_index=None):
        # Does not call super(): this analysis never queries Elasticsearch. It accepts but ignores the index args.
        self.elasticsearch_conn = None
        self.network = network
        self.falco_index = falco_index
        self.sysflow_index = sysflow_index
        self.parsed_telemetry_ids = set()
        self.monitoring_start = None

    def get_new_telemetry(self) -> list[dict]:
        # Override the parent, whose get_new_telemetry() calls search() on a None connection here.
        return []

    def process_low_level_events(self, new_telemetry: list[dict]) -> list[Event]:
        return []
