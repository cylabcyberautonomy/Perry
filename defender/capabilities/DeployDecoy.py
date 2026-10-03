from defender.capabilities import Action
from environment.network import Subnet


class DeployDecoy(Action):
    def __init__(
        self,
        subnet: Subnet,
        host_name: str = "decoy_host",
        apacheVulnerability: bool = False,
        honeySSHService: bool = False,
    ):
        super().__init__()
        self.subnet = subnet
        self.host_name = host_name
        self.apacheVulnerability = apacheVulnerability
        self.honeySSHService = honeySSHService
