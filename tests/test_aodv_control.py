import sys
import threading
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from aodv_control import process_control_command
from aodv_models import RouteEntry


class DummyProtocol:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.routing_table: dict[str, RouteEntry] = {}
        self.neighbor_table = {}
        self.message_box = []
        self.pending_data_packets = {}
        self.addr_alias = {}
        self.error_manager = type("EM", (), {"precursors": {}})()
        self.discovery_manager = type("DM", (), {"snapshot": lambda self: {}})()
        self.rrep_ack_manager = type("AM", (), {"snapshot": lambda self: {}})()
        self.local_repair_manager = type("LM", (), {"snapshot": lambda self: {}})()
        self.config = type(
            "Cfg",
            (),
            {
                "hello_interval_sec": 10,
                "hello_timeout_sec": 30,
                "route_lifetime_sec": 300,
                "path_discovery_timeout_sec": 30,
                "rreq_ttl": 16,
                "rreq_ttl_start": 2,
                "rreq_ttl_increment": 2,
                "rreq_ttl_threshold": 7,
                "rreq_retry_wait_sec": 2,
                "rreq_retries": 3,
                "local_repair_wait_sec": 5,
                "rrep_ack_timeout_sec": 2,
                "rerr_rate_limit_sec": 1,
                "tx_jitter_max_ms": 30,
            },
        )()
        self.node_status = "ACTIVE"

    def resolve_address(self, target: str) -> str | None:
        return target

    def _touch_neighbor(self, neighbor_addr: str, neighbor_ip: str) -> None:
        return None

    def _send_user_data(self, dest_addr: str, payload: str) -> str:
        return f"send:{dest_addr}:{payload}"


class TestAodvControlRouteFormat(unittest.TestCase):
    def test_show_route_compact_table_format(self) -> None:
        protocol = DummyProtocol()
        protocol.routing_table["10.0.0.4"] = RouteEntry(
            dest_addr="10.0.0.4",
            next_hop="10.0.0.2",
            next_hop_ip="10.0.0.2",
            hop_count=2,
            dest_seq_num=1,
            valid=True,
            route_state="VALID",
            expires_at=100.0,
        )
        protocol.routing_table["10.0.0.3"] = RouteEntry(
            dest_addr="10.0.0.3",
            next_hop="10.0.0.3",
            next_hop_ip="10.0.0.3",
            hop_count=1,
            dest_seq_num=1,
            valid=True,
            route_state="VALID",
            expires_at=100.0,
        )
        protocol.routing_table["10.0.0.9"] = RouteEntry(
            dest_addr="10.0.0.9",
            next_hop="10.0.0.8",
            next_hop_ip="10.0.0.8",
            hop_count=3,
            dest_seq_num=1,
            valid=False,
            route_state="INVALID",
            expires_at=100.0,
        )

        text = process_control_command(protocol, "SHOW_ROUTE")
        self.assertIn("Destination", text)
        self.assertIn("Next Hop", text)
        self.assertIn("Distance", text)
        self.assertIn("10.0.0.3", text)
        self.assertIn("10.0.0.2", text)
        self.assertIn("1.0", text)
        self.assertIn("2.0", text)
        self.assertNotIn("10.0.0.9", text)


if __name__ == "__main__":
    unittest.main()
