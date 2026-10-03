from environment.network import Host
from defender.capabilities import Action, DeployDecoy, DeployDecoy, AddFakeData

from defender.telemetry.events import Event
from . import Strategy

from utility.logging import log_event

import time


class NaiveDecoyHost(Strategy):
    ARMS_IN_SETUP = True

    def initialize(self):
        log_event("NaiveDecoyHost", "Initializing NaiveDecoyHost strategy")
        num_decoys = self.arsenal.storage.get("DeployDecoy", self._default_decoy_count())
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

        # Wait for decoy hosts to deploy
        time.sleep(15)

        for decoy in self.network.get_all_decoys():
            self.orchestrator.run([AddFakeData(decoy)])


    def run(self):
        pass
