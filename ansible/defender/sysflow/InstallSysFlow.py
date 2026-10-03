import os
import json

from ansible.AnsiblePlaybook import AnsiblePlaybook
from config.config import Config

PIPELINE_PATH = os.path.join(os.path.dirname(__file__), "pipeline.local.json")
PIPELINE_TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "pipeline_template.local.json"
)


class InstallSysFlow(AnsiblePlaybook):
    def __init__(self, hosts: str | list[str], elastic_config: Config) -> None:
        self.name = "defender/sysflow/configure_and_start_sysflow.yml"
        self.params = {"host": hosts}

        with open(PIPELINE_TEMPLATE_PATH, "r") as f:
            pipeline_template = json.load(f)

        for processor in pipeline_template["pipeline"]:
            if processor["processor"] == "exporter":
                # http, not https: this Elasticsearch runs plain HTTP with xpack.security disabled.
                processor["es.addresses"] = (
                    "http://"
                    + elastic_config.external_ip
                    + ":"
                    + str(elastic_config.elastic_config.port)
                )
                processor["es.username"] = "elastic"
                processor["es.password"] = elastic_config.elastic_config.api_key
                # Per-experiment index: the shared ES reuses host names and IPs across topologies.
                processor["es.index"] = elastic_config.sysflow_index

        with open(PIPELINE_PATH, "w") as f:
            json.dump(pipeline_template, f)


class ReconfigureSysFlow(InstallSysFlow):
    """Like InstallSysFlow, but for a host where sysflow already runs the baked config, so it replaces the config and restarts the services."""

    def __init__(self, hosts: str | list[str], elastic_config: Config) -> None:
        super().__init__(hosts, elastic_config)
        self.name = "defender/sysflow/reconfigure_sysflow.yml"
