from environment.network import Host
from defender.capabilities import (
    DeployDecoy,
    AddHoneyCredentials,
    RestoreServer,
    AddFakeData,
)

import time

from defender.telemetry.events import (
    DecoyHostInteraction,
    DecoyCredentialUsed,
)
from . import Strategy

# Minimum seconds between rebuilds of the same host.
RESTORE_COOLDOWN_SECONDS = 60
from defender.capabilities.RestoreServer import sensitive_subnets

from utility.logging import log_event


class ReactiveLayered(Strategy):
    def initialize(self):
        log_event("ReactiveLayered", "Initializing ReactiveLayered strategy")
        num_decoys = self.arsenal.storage.get("DeployDecoy", self._default_decoy_count())
        num_honeycreds = self.arsenal.storage.get("HoneyCredentials", num_decoys)

        # Running tally only. No budget caps the restores.
        self.restore_count = 0
        # host ip -> monotonic time of the last rebuild.
        self.last_restored: dict[str, float] = {}
        # honey decoy_user -> IP of the planting host.
        self.honeycred_origin: dict[str, str] = {}
        # honey decoy_user -> IP of the decoy that credential reaches.
        self.honeycred_decoy: dict[str, str] = {}

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

            self.orchestrator.run([AddFakeData(decoy)])

        # Wait for decoy hosts to deploy
        time.sleep(15)

        for decoy in self.network.get_all_decoys():

            self.orchestrator.run([AddFakeData(decoy)])

        # Place honey credentials, at least one on the attacker's entry path.
        for deploy_host in self._honeycred_deploy_hosts(num_honeycreds):
            decoy_host = self.network.get_random_decoy()

            # Capture the Faker-generated honey username by comparing decoy_users around the run.
            before = set(decoy_host.decoy_users)
            self.orchestrator.run(
                [AddHoneyCredentials(deploy_host, decoy_host, 1, real=True)]
            )
            for new_user in set(decoy_host.decoy_users) - before:
                self.honeycred_origin[new_user] = deploy_host.ip
                self.honeycred_decoy[new_user] = decoy_host.ip

        self.telemetry_service.subscribe(
            DecoyCredentialUsed, self.handle_decoy_interaction
        )
        self.telemetry_service.subscribe(
            DecoyHostInteraction, self.handle_decoy_interaction
        )

    def _restore_throttled(self, host_ip: str | None) -> None:
        """Restore host_ip unless a rebuild happened within RESTORE_COOLDOWN_SECONDS."""
        if not host_ip:
            return
        last = self.last_restored.get(host_ip)
        now = time.monotonic()
        if last is not None and now - last < RESTORE_COOLDOWN_SECONDS:
            return
        # Skip sensitive subnets so a no-op restore does not reset the cooldown or the tally.
        if any(subnet in host_ip for subnet in sensitive_subnets):
            return
        self.last_restored[host_ip] = now
        self.restore_count += 1
        log_event(
            "ReactiveLayered",
            f"Restoring {host_ip} (#{self.restore_count}, no budget cap)",
        )
        self.orchestrator.run([RestoreServer(host_ip)])

    def handle_decoy_interaction(
        self, event: DecoyCredentialUsed | DecoyHostInteraction
    ):
        if not isinstance(event, DecoyCredentialUsed):
            self._restore_throttled(event.target_ip)

        self._restore_throttled(event.source_ip)

        # A used honey credential also condemns its planting host, so restore it too.
        if isinstance(event, DecoyCredentialUsed):
            origin_ip = self.honeycred_origin.get(event.decoy_user)
            if origin_ip and origin_ip != event.source_ip:
                self._restore_throttled(origin_ip)

            # Refresh the decoy the credential reaches, so it drops the attacker's session.
            decoy_ip = self.honeycred_decoy.get(event.decoy_user)
            if decoy_ip:
                self._restore_throttled(decoy_ip)

    def run(self):
        pass
