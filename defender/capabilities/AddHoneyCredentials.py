from . import Action
from environment.network import Host


class AddHoneyCredentials(Action):
    def __init__(
        self,
        credential_host: Host,
        honey_host: Host,
        number: int = 1,
        real: bool = True,
        fakeData: bool = True,
        honey_user: str | None = None,
        file_name: str = "decoy.json",
        file_content: str = "data.json",
    ):
        self.credential_host = credential_host
        self.honey_host = honey_host
        self.number = number
        self.real = real
        self.fakeData = fakeData
        self.honey_user = honey_user
        self.file_name = "~/" + file_name
        self.file_content = file_content
