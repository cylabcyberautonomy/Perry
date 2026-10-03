from defender.capabilities import (
    AddHoneyCredentials,
)

from . import Strategy

from utility.logging import log_event


class NaiveDecoyCredential(Strategy):
    ARMS_IN_SETUP = True

    def initialize(self):
        log_event("StaticStandalone", "Initializing StaticStandalone strategy")
        num_honeycreds = self.arsenal.storage["HoneyCredentials"]

        credential_actions = []
        credentials_per_subnet = int(num_honeycreds / len(self.network.subnets))
        for subnet in self.network.subnets:
            for i in range(0, credentials_per_subnet):
                deploy_host = subnet.get_random_host()
                target_host = self.network.get_random_host()
                credential_actions.append(
                    AddHoneyCredentials(deploy_host, target_host, 1, real=False)
                )

        self.orchestrator.run(credential_actions)

    def run(self):
        pass
