from defender.capabilities import Action

# Subnets a restore must NEVER touch (attacker foothold + management planes) — a backend-neutral policy
# constant, kept with the capability so no strategy has to import the (deleted) backend actuator for it.
sensitive_subnets = ["192.168.202", "192.168.198", "10.0.0"]


class RestoreServer(Action):
    def __init__(self, host_ip: str):
        super().__init__()

        self.host_ip = host_ip
