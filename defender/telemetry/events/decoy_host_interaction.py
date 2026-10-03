from .event import Event


class DecoyHostInteraction(Event):

    def __init__(self, source_ip: str, target_ip: str) -> None:
        super().__init__()

        self.source_ip = source_ip
        self.target_ip = target_ip
