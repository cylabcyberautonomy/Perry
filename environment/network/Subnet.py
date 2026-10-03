from . import Host
import random


class Subnet:
    def __init__(
        self,
        name: str,
        hosts: list[Host],
        sec_group: str,
        attacker: bool = False,
        entry: bool = False,
    ):
        self.name = name
        self.hosts: list[Host] = hosts
        self.sec_group = sec_group
        self.decoys: list[Host] = []
        # True for a subnet directly connected to the attacker's segment.
        self.entry = entry
        # True for the subnet the red team starts in.
        self.attacker = attacker

    def add_host(self, host: Host, decoy=False):
        if decoy:
            self.decoys.append(host)
        else:
            self.hosts.append(host)

    def get_random_host(self) -> Host:
        return random.choice(self.hosts)
