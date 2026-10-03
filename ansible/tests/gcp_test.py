from ansible.AnsibleRunner import AnsibleRunner
from ansible.AnsiblePlaybook import AnsiblePlaybook


def main():
    ansible_runner = AnsibleRunner(
        ssh_key_path="~/.ssh/id_rsa",
        management_ip="10.10.10.10",
        ansible_dir="ansible",
        log_path="output",
        inventory_file="inventory.gcp.yml",
        config_file="configs/ansible.gcp.cfg",
    )

    result = ansible_runner.run_playbook(
        AnsiblePlaybook(name="common/ping.yml", host="all")
    )

    print(f"Result status: {result.status}")
    print(f"Return code: {result.rc}")


if __name__ == "__main__":
    main()
