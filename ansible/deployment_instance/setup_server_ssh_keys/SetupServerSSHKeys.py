from ansible.AnsiblePlaybook import AnsiblePlaybook


class SetupServerSSHKeys(AnsiblePlaybook):
    def __init__(
        self,
        host: str,
        host_user: str,
        follower: str,
        follower_user: str,
    ) -> None:
        self.name = "deployment_instance/setup_server_ssh_keys/setup_ssh_keys.yml"

        self.params = {
            "from_host_ip": host,
            "from_user": host_user,
            "to_host_ip": follower,
            "to_user": follower_user,
        }
