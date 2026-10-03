from . import Subnet, Host
import random


class Network:
    def __init__(self, name: str, subnets: list[Subnet], management_sg: str | None = None):
        self.name = name
        self.subnets = subnets
        self.num_honey_credentials = 0
        # Management security group that decoys attach to. Defaults to the actuator fallback.
        self.management_sg = management_sg

    def get_all_hosts(self) -> list[Host]:
        hosts = []
        for subnet in self.subnets:
            hosts.extend(subnet.hosts)
        return hosts

    def get_all_host_ips(self) -> list[str]:
        return [host.ip for host in self.get_all_hosts()]

    @staticmethod
    def _normalize_hostname(name: str) -> str:
        """Return the canonical form of a hostname, without domain suffix, case, or hyphens."""
        return name.strip().split(".")[0].lower().replace("-", "_")

    def get_host_by_name(self, name: str) -> Host | None:
        if name is None:
            return None
        canon = name.replace("-", "_")
        for subnet in self.subnets:
            for host in subnet.hosts:
                if host.name == name or host.name == canon or host.name == canon.replace("_", "-"):
                    return host
        # Fallback tolerates a domain suffix and case.
        target = self._normalize_hostname(name)
        for subnet in self.subnets:
            for host in subnet.hosts:
                if self._normalize_hostname(host.name) == target:
                    return host
        return None

    def get_all_decoys(self) -> list[Host]:
        decoys = []
        for subnet in self.subnets:
            decoys.extend(subnet.decoys)
        return decoys

    def get_random_decoy(self) -> Host:
        return random.choice(self.get_all_decoys())

    def get_random_host(self) -> Host:
        return random.choice(self.get_all_hosts())

    def get_random_subnet(self) -> Subnet:
        """Return a random subnet for deception placement, never the attacker's own."""
        candidates = [subnet for subnet in self.subnets if not getattr(subnet, "attacker", False)]
        return random.choice(candidates or self.subnets)

    def get_subnet_by_name(self, name: str) -> Subnet | None:
        for subnet in self.subnets:
            if subnet.name == name:
                return subnet
        return None

    def is_ip_decoy(self, ip: str):
        decoys = self.get_all_decoys()
        for decoy in decoys:
            if decoy.ip == ip:
                return True

        return False

    def get_all_decoy_users(self):
        all_decoy_users = []
        all_hosts = self.get_all_hosts()

        for host in all_hosts:
            all_decoy_users.extend(host.decoy_users)

        return all_decoy_users
