from environment.network import Host
from defender.capabilities import (
    DeployDecoy,
    AddHoneyCredentials,
    AddFakeData,
)

from defender.strategy import Strategy
import time


class StaticLayered(Strategy):
    ARMS_IN_SETUP = True

    def initialize(self):
        num_decoys = self.arsenal.storage.get("DeployDecoy", self._default_decoy_count())
        num_honeycreds = self.arsenal.storage.get("HoneyCredentials", num_decoys)

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
        # Wait for decoy hosts to deploy
        time.sleep(15)

        for decoy in self.network.get_all_decoys():

            self.orchestrator.run([AddFakeData(decoy, file_content="data.json")])

        # Place honey credentials, at least one on the attacker's entry path.
        for deploy_host in self._honeycred_deploy_hosts(num_honeycreds):
            target_host = self.network.get_random_decoy()

            self.orchestrator.run(
                [
                    AddHoneyCredentials(
                        deploy_host, target_host, 1, real=True, fakeData=True
                    )
                ]
            )

    def run(self):
        pass
