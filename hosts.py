import lib, hostgroups


def get_hosts(group=None):
    """Fetch, print, and return host/id/status info, optionally filtered to the given host group name."""
    params = {"output": ["hostid", "host", "status"]}
    if group:
        group_id = hostgroups.hostgroup_id(group)
        if not group_id:
            return []
        params["groupids"] = [group_id]

    hosts = lib.call("host.get", params)
    if not hosts:
        return []

    host_list = []
    for host in hosts:
        host_info = {
            "name": host["host"],
            "id": host["hostid"],
            "enabled": host["status"] == "0",
        }
        host_list.append(host_info)
        print(host_info["name"], host_info["id"], "enabled" if host_info["enabled"] else "disabled")

    return host_list


if __name__ == "__main__":
    print(hostgroups.get_hostgroups())
    get_hosts()
