from .event import Event


class SuspiciousHost(Event):
    def __init__(self, host_name: str) -> None:
        super().__init__()

        self.host_name = host_name
