"""AODV 邻居管理器。"""

from aodv_models import NeighborEntry


class NeighborManager:
    def __init__(self, neighbor_table: dict[str, NeighborEntry], addr_alias: dict[str, str]):
        self.neighbor_table = neighbor_table
        self.addr_alias = addr_alias

    def touch(self, neighbor_addr: str, neighbor_ip: str, now: float) -> NeighborEntry:
        self.addr_alias[neighbor_addr] = neighbor_ip
        self.addr_alias[neighbor_ip] = neighbor_ip

        entry = self.neighbor_table.get(neighbor_addr)
        if entry is None:
            entry = NeighborEntry(node_id=neighbor_addr, ip=neighbor_ip, last_hello_ts=now)
            self.neighbor_table[neighbor_addr] = entry
        else:
            entry.ip = neighbor_ip
            entry.last_hello_ts = now
        return entry

    def remove(self, neighbor_addr: str) -> None:
        self.neighbor_table.pop(neighbor_addr, None)

    def stale_neighbors(self, now: float, hello_timeout_sec: int) -> list[str]:
        stale = []
        for addr, entry in self.neighbor_table.items():
            if now - entry.last_hello_ts > hello_timeout_sec:
                stale.append(addr)
        return stale

    def all_neighbor_ips(self) -> list[str]:
        return [entry.ip for entry in self.neighbor_table.values()]
