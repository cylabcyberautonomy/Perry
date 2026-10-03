from .events import Event
from elasticsearch import Elasticsearch
from environment.network import Network
from .index_names import FALCO_BASE, SYSFLOW_BASE

from abc import ABC, abstractmethod

from utility.logging import PerryLogger

logger = PerryLogger.get_logger()


class TelemetryAnalysis(ABC):
    def __init__(
        self,
        elasticsearch_conn: Elasticsearch,
        network: Network,
        falco_index: str = FALCO_BASE,
        sysflow_index: str = SYSFLOW_BASE,
    ):
        self.elasticsearch_conn = elasticsearch_conn
        self.network = network
        # Indices for this experiment only. The shared Elasticsearch has no run discriminator, so the unscoped indices mix runs.
        self.falco_index = falco_index
        self.sysflow_index = sysflow_index
        self.parsed_telemetry_ids = set()
        # Ignore telemetry recorded before arming (provisioning, telemetry startup, the defender's own arming).
        self.monitoring_start = None

        if not self.elasticsearch_conn.indices.exists(index=self.sysflow_index):
            self.elasticsearch_conn.indices.create(index=self.sysflow_index)

        # Create the falco index too: on a fresh environment the unconditional falco query 404s and kills the defender if it is missing.
        if not self.elasticsearch_conn.indices.exists(index=self.falco_index):
            self.elasticsearch_conn.indices.create(index=self.falco_index)

    def begin_monitoring(self) -> None:
        """Mark now as the scenario start, so later queries drop provisioning and arming activity."""
        from datetime import datetime, timezone

        self.monitoring_start = datetime.now(timezone.utc).isoformat()

    def get_new_telemetry(self) -> list[dict]:
        # Recency window plus a hard floor at scenario start. The window is wide because sf-processor indexes decoy events tens of seconds after their @timestamp.
        time_bounds = [{"range": {"@timestamp": {"gte": "now-180s"}}}]
        if self.monitoring_start is not None:
            time_bounds.append(
                {"range": {"@timestamp": {"gte": self.monitoring_start}}}
            )

        ssh_process = {
            "bool": {
                "must": time_bounds
                + [
                    {
                        "bool": {
                            "should": [
                                {"match": {"event.category": "process"}},
                                {"match": {"process.name": "ssh"}},
                            ]
                        }
                    },
                ]
            }
        }

        network_traces = {
            "bool": {
                "must": time_bounds
                + [
                    {
                        "bool": {
                            "should": [
                                {"match": {"event.category": "network"}},
                            ]
                        }
                    },
                ]
            }
        }

        # size=10000 because a busy host emits far more than 10 docs per window. unmapped_type="date" avoids a 400 when sorting an empty scoped index.
        _sort = [{"@timestamp": {"order": "desc", "unmapped_type": "date"}}]
        falco_data = self.elasticsearch_conn.search(
            index=self.falco_index,
            query={"bool": {"must": time_bounds}},
            size=10000,
            sort=_sort,
        )
        process_data = self.elasticsearch_conn.search(
            index=self.sysflow_index, query=ssh_process, size=10000, sort=_sort
        )
        traces_data = self.elasticsearch_conn.search(
            index=self.sysflow_index, query=network_traces, size=10000, sort=_sort
        )

        raw_telemetry = (
            process_data["hits"]["hits"]
            + traces_data["hits"]["hits"]
            + falco_data["hits"]["hits"]
        )

        new_telemetry = [
            alert
            for alert in raw_telemetry
            if alert["_id"] not in self.parsed_telemetry_ids
        ]

        new_document_ids = [alert["_id"] for alert in new_telemetry]
        self.parsed_telemetry_ids.update(new_document_ids)

        return new_telemetry

    @abstractmethod
    def process_low_level_events(self, new_telemetry: list[dict]) -> list[Event]:
        pass
