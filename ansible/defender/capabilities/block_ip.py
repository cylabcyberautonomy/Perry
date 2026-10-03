from ansible.AnsiblePlaybook import AnsiblePlaybook


class BlockIP(AnsiblePlaybook):
    def __init__(self, hosts: list[str], ip_to_block: str, port: int) -> None:
        self.name = "defender/capabilities/block_ip.yml"
        self.params = {
            "hosts": hosts,
            "ip_to_block": ip_to_block,
            "port_to_block": port,
        }
