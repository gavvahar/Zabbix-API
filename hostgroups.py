import lib


def get_hostgroups():
    """Fetch all host groups and return their name and id."""
    hostgroups = lib.call("hostgroup.get", {"output": ["groupid", "name"]})
    if not hostgroups:
        return []

    group_list = []
    for group in hostgroups:
        group_list.append({"name": group["name"], "id": group["groupid"]})

    return group_list


def hostgroup_id(name):
    """Look up the host group id for the given group name."""
    for group in get_hostgroups():
        if group["name"] == name:
            return group["id"]
    return None


if __name__ == "__main__":
    print(get_hostgroups())
