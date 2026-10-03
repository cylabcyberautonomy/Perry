from environment.network import Host
from defender.capabilities import (
    DeployDecoy,
    AddHoneyCredentials,
    AddFakeData,
)

from defender.strategy import Strategy
import time


class StaticLayeredFileContent(Strategy):
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

            self.orchestrator.run([AddFakeData(decoy, file_content="decoy.json")])

        credentials_per_subnet = int(num_honeycreds / len(self.network.subnets))
        extra_credentials = num_honeycreds % len(self.network.subnets)
        for subnet in self.network.subnets:
            for i in range(0, credentials_per_subnet):
                deploy_host = subnet.get_random_host()
                target_host = self.network.get_random_decoy()

                self.orchestrator.run(
                    [
                        AddHoneyCredentials(
                            deploy_host, target_host, 1, real=True, fakeData=True, file_content="decoy.json"
                        )
                    ]
                )

        for i in range(0, extra_credentials):
            subnet = self.network.get_random_subnet()
            deploy_host = subnet.get_random_host()
            target_host = self.network.get_random_decoy()
            self.orchestrator.run(
                [
                    AddHoneyCredentials(
                        deploy_host, target_host, 1, real=True, fakeData=True, file_content="decoy.json"
                    )
                ]
            )

    def run(self):
        pass
