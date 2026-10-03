from environment.network import Host
from defender.capabilities import (
    DeployDecoy,
    AddHoneyCredentials,
    RestoreServer,
)

from defender.telemetry.events import (
    DecoyHostInteraction,
    DecoyCredentialUsed,
)
from . import Strategy

from utility.logging import log_event


class ReactiveStandalone(Strategy):
    def initialize(self):
        num_decoys = self.arsenal.storage.get("DeployDecoy", self._default_decoy_count())
        num_honeycreds = self.arsenal.storage.get("HoneyCredentials", num_decoys)

        self.restore_count = 0
        self.max_restores = self.arsenal.storage["RestoreServer"]

        actions = []
        for i in range(0, num_decoys):
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

        self.telemetry_service.subscribe(
            DecoyCredentialUsed, self.handle_decoy_interaction
        )
        self.telemetry_service.subscribe(
            DecoyHostInteraction, self.handle_decoy_interaction
        )

    def handle_decoy_interaction(
        self, event: DecoyCredentialUsed | DecoyHostInteraction
    ):
        if not isinstance(event, DecoyCredentialUsed):
            self.orchestrator.run([RestoreServer(event.target_ip)])

        self.orchestrator.run([RestoreServer(event.source_ip)])

    def run(self):
        pass
