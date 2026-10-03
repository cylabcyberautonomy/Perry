from environment.network import Host
from defender.capabilities import (
    DeployDecoy,
    AddHoneyCredentials,
)

from defender.strategy import Strategy

from utility.logging import log_event


class StaticStandalone(Strategy):
    ARMS_IN_SETUP = True

    def initialize(self):
        log_event("StaticStandalone", "Initializing StaticStandalone strategy")
        num_decoys = self.arsenal.storage.get("DeployDecoy", self._default_decoy_count())
        num_honeycreds = self.arsenal.storage.get("HoneyCredentials", num_decoys)
        actions = []

        for i in range(0, num_decoys):
            subnet_to_deploy = self.network.get_subnet_by_name("webserver_network")

            if subnet_to_deploy is None:
                subnet_to_deploy = self.network.get_random_subnet()

            decoy_name = f"decoy_{i}"
            decoy_action = DeployDecoy(
                subnet=subnet_to_deploy,
                host_name=decoy_name,
                apacheVulnerability=False,
            )
            actions.append(decoy_action)

        self.orchestrator.run(actions)

        credentials_per_subnet = int(num_honeycreds / len(self.network.subnets))
        for subnet in self.network.subnets:
            for i in range(0, credentials_per_subnet):
                deploy_host = subnet.get_random_host()
                target_host = self.network.get_random_host()

                self.orchestrator.run(
                    [AddHoneyCredentials(deploy_host, target_host, 1, real=False)]
                )

    def run(self):
        pass
