from .event import Event


class AttackerOnHost(Event):

    def __init__(self, attacker_ip) -> None:
        super().__init__()

        self.attacker_ip = attacker_ip
