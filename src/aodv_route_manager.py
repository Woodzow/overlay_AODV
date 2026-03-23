"""AODV 路由管理器。"""

from aodv_models import RouteEntry
from aodv_sequence import is_seq_newer


class RouteManager:
    def __init__(self, routing_table: dict[str, RouteEntry]):
        self.routing_table = routing_table

    def upsert_connected(self, dest_addr: str, next_hop_ip: str, now: float, lifetime_sec: int) -> RouteEntry:
        old = self.routing_table.get(dest_addr)
        seq = max(1, old.dest_seq_num) if old else 1
        route = RouteEntry(
            dest_addr=dest_addr,
            next_hop=dest_addr,
            next_hop_ip=next_hop_ip,
            hop_count=1,
            dest_seq_num=seq,
            valid=True,
            route_state="VALID",
            expires_at=now + lifetime_sec,
        )
        self.routing_table[dest_addr] = route
        return route

    def should_replace(self, old: RouteEntry, new: RouteEntry) -> bool:
        if not old.valid and new.valid:
            return True
        if is_seq_newer(new.dest_seq_num, old.dest_seq_num):
            return True
        if new.dest_seq_num == old.dest_seq_num and new.hop_count < old.hop_count:
            return True
        return False

    def upsert_discovered(self, new_route: RouteEntry) -> None:
        old = self.routing_table.get(new_route.dest_addr)
        if old is None or self.should_replace(old, new_route):
            new_route.valid = True
            new_route.route_state = "VALID"
            self.routing_table[new_route.dest_addr] = new_route
            return
        old.expires_at = max(old.expires_at, new_route.expires_at)
        if new_route.valid:
            old.valid = True
            old.route_state = "VALID"

    def get_valid(self, dest_addr: str, now: float) -> RouteEntry | None:
        route = self.routing_table.get(dest_addr)
        if route is None:
            return None
        if (not route.valid) or route.route_state != "VALID" or route.expires_at <= now:
            return None
        return route

    def invalidate(self, dest_addr: str, seq_num: int, now: float, hold_sec: int) -> RouteEntry | None:
        route = self.routing_table.get(dest_addr)
        if route is None:
            return None
        route.valid = False
        route.route_state = "INVALID"
        if is_seq_newer(seq_num, route.dest_seq_num):
            route.dest_seq_num = seq_num
        route.expires_at = now + hold_sec
        return route

    def mark_local_repairing(self, dest_addr: str, now: float, wait_sec: int) -> RouteEntry | None:
        route = self.routing_table.get(dest_addr)
        if route is None:
            return None
        route.valid = False
        route.route_state = "REPAIRING"
        route.expires_at = now + max(1, wait_sec)
        return route

    def invalidate_via_next_hop(self, next_hop: str, now: float, hold_sec: int) -> list[dict]:
        changed: list[dict] = []
        for route in self.routing_table.values():
            if route.next_hop != next_hop:
                continue
            if not route.valid:
                continue
            route.valid = False
            route.route_state = "INVALID"
            route.dest_seq_num = (route.dest_seq_num + 1) & 0xFFFFFFFF
            route.expires_at = now + hold_sec
            changed.append({"dest_addr": route.dest_addr, "dest_seq_num": route.dest_seq_num})
        return changed

    def expire_routes(self, now: float) -> None:
        for route in self.routing_table.values():
            if route.expires_at <= now:
                route.valid = False
                if route.route_state == "REPAIRING":
                    route.route_state = "INVALID"
