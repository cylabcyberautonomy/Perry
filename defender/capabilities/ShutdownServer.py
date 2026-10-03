from defender.capabilities import Action


class ShutdownServer(Action):
    def __init__(self, host_ip: str):
        super().__init__()

        self.host_ip = host_ip
