from defender.capabilities import Action
from environment.network import Host


class StartHoneyService(Action):
    def __init__(self, host: Host, port_no: str = "8000", service: str = "ssh"):
        super().__init__()

        self.host = host
        self.port_no = port_no
        self.service = service
