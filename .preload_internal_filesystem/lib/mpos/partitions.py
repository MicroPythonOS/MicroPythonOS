def get_next_update_partition(partition_module=None):
    if partition_module is None:
        from esp32 import Partition
        partition_module = Partition
    current = partition_module(partition_module.RUNNING)
    cur = current.info()[4]
    nxt = "ota_0" if cur == "ota_1" else "ota_1"
    partitions = partition_module.find(partition_module.TYPE_APP, label=nxt)
    if not partitions:
        raise Exception(f"Could not find partition: {nxt}")
    return partitions[0]
