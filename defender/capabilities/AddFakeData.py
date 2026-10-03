from . import Action
from environment.network import Host
from typing import Optional


class AddFakeData(Action):
    def __init__(
        self,
        host: Host,
        file_name: Optional[str] = "decoy.json",
        user: Optional[str] = None,
        path: Optional[str] = "~/",
        file_content: Optional[str] = "data.json",
    ):
        self.host = host
        self.file_name = file_name
        self.user = user
        self.path = path
        self.file_content = file_content
