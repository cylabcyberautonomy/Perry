from ansible.AnsibleRunner import AnsibleRunner
from ansible.AnsiblePlaybook import AnsiblePlaybook


def main():
    ansible_runner = AnsibleRunner(
        ssh_key_path="~/perry_key.pem",
        management_ip="172.24.4.15",
        ansible_dir="./ansible/",
        log_path="output",
        inventory_file="inventory.openstack",
    )

    result = ansible_runner.run_playbook(
        AnsiblePlaybook(name="common/ping.yml", host="all")
    )

    print(f"Result status: {result.status}")
    print(f"Return code: {result.rc}")


if __name__ == "__main__":
    main()
