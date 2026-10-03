from ansible.AnsiblePlaybook import AnsiblePlaybook


class SetupNetcatShell(AnsiblePlaybook):
    def __init__(self, hosts: str | list[str], user: str) -> None:
        self.name = "vulnerabilities/NetcatShell.yml"
        self.params = {
            "to_host_ip": hosts,
            "to_user": user,
        }
