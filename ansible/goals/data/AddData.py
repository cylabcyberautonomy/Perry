from ansible.AnsiblePlaybook import AnsiblePlaybook


class AddData(AnsiblePlaybook):
    def __init__(
        self, host: str, host_user: str, path: str, file_content: str = "data.json"
    ) -> None:
        self.name = "goals/data/addData.yml"
        self.params = {
            "host": host,
            "host_user": host_user,
            "dst_path": path,
            "src_path": file_content,
        }
