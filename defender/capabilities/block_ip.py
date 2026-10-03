from . import Action


class BlockIP(Action):
    def __init__(
        self,
        ip_to_block: str,
        port: int,
    ):
        self.ip_to_block = ip_to_block
        self.port = port
