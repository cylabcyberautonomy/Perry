from ansible.AnsiblePlaybook import AnsiblePlaybook
from config.config import Config


class InstallFalco(AnsiblePlaybook):
    def __init__(self, hosts: str | list[str], config: Config) -> None:
        self.name = "defender/falco/install_falco.yml"

        # http, not https: this shared Elasticsearch runs with xpack.security.enabled=false.
        es_host = f"http://{config.external_ip}:{config.elastic_config.port}"

        self.params = {
            "host": hosts,
            "es_address": es_host,
            "es_user": "elastic",
            "es_password": config.elastic_config.api_key,
            # Per-experiment index: a falco document carries no experiment field, so concurrent experiments would collide on the bare "falco".
            "es_index": config.falco_index,
        }
