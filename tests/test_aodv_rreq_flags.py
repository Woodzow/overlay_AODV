import sys
import time
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "Src"))

from aodv_codec import (
    RREQ_FLAG_DEST_ONLY,
    RREQ_FLAG_GRATUITOUS,
    RREQ_FLAG_JOIN,
    RREQ_FLAG_REPAIR,
    RREQ_FLAG_UNKNOWN_SEQ,
)
from aodv_config import NodeConfig
from aodv_models import RouteEntry
from aodv_protocol import AodvProtocol


class TestAodvRreqFlags(unittest.TestCase):
    def _new_protocol(self) -> AodvProtocol:
        config = NodeConfig(
            node_id="n1",
            node_ip="10.0.0.1",
            bind_ip="0.0.0.0",
            overlay_port=5005,
            control_bind_ip="0.0.0.0",
            control_port=5101,
            neighbors=[],
        )
        protocol = AodvProtocol(config)
        protocol.logger = type("DummyLogger", (), {"debug": lambda *a, **k: None, "exception": lambda *a, **k: None})()
        return protocol

    def test_start_route_discovery_sets_unknown_seq_flag(self) -> None:
        protocol = self._new_protocol()
        broadcasts: list[dict] = []
        protocol._broadcast_to_neighbors = lambda packet, exclude_node=None: broadcasts.append(dict(packet))

        protocol._start_route_discovery("10.0.0.9", dest_seq_num=0, force=True)

        self.assertEqual(len(broadcasts), 1)
        self.assertTrue(broadcasts[0]["flags"] & RREQ_FLAG_UNKNOWN_SEQ)

    def test_start_route_discovery_sets_repair_flag(self) -> None:
        protocol = self._new_protocol()
        broadcasts: list[dict] = []
        protocol._broadcast_to_neighbors = lambda packet, exclude_node=None: broadcasts.append(dict(packet))

        protocol._start_route_discovery("10.0.0.9", dest_seq_num=7, force=True, is_local_repair=True)

        self.assertEqual(len(broadcasts), 1)
        self.assertTrue(broadcasts[0]["flags"] & RREQ_FLAG_REPAIR)

    def test_rreq_dest_only_does_not_use_intermediate_reply(self) -> None:
        protocol = self._new_protocol()
        now = time.time()
        protocol.route_manager.upsert_connected("10.0.0.9", "10.0.0.2", now=now, lifetime_sec=60)

        sent_rrep: list[tuple] = []
        broadcasted: list[dict] = []
        protocol._send_rrep = lambda *args, **kwargs: sent_rrep.append((args, kwargs))
        protocol._broadcast_to_neighbors = lambda packet, exclude_node=None: broadcasted.append(dict(packet))

        packet = {
            "type": "RREQ",
            "sender": "10.0.0.2",
            "flags": RREQ_FLAG_DEST_ONLY,
            "hop_count": 1,
            "ttl": 6,
            "rreq_id": 11,
            "dest_addr": "10.0.0.9",
            "dest_seq_num": 1,
            "orig_addr": "10.0.0.7",
            "orig_seq_num": 5,
        }
        protocol._process_rreq(packet, sender_ip="10.0.0.2")

        self.assertEqual(len(sent_rrep), 0)
        self.assertEqual(len(broadcasted), 1)

    def test_rreq_gratuitous_adds_second_rrep(self) -> None:
        protocol = self._new_protocol()
        now = time.time()
        protocol.route_manager.upsert_discovered(
            RouteEntry(
                dest_addr="10.0.0.9",
                next_hop="10.0.0.3",
                next_hop_ip="10.0.0.3",
                hop_count=1,
                dest_seq_num=10,
                valid=True,
                route_state="VALID",
                expires_at=now + 60,
            )
        )

        sent_rrep: list[tuple] = []
        protocol._send_rrep = lambda *args, **kwargs: sent_rrep.append((args, kwargs))

        packet = {
            "type": "RREQ",
            "sender": "10.0.0.2",
            "flags": RREQ_FLAG_GRATUITOUS,
            "hop_count": 1,
            "ttl": 6,
            "rreq_id": 12,
            "dest_addr": "10.0.0.9",
            "dest_seq_num": 1,
            "orig_addr": "10.0.0.7",
            "orig_seq_num": 9,
        }
        protocol._process_rreq(packet, sender_ip="10.0.0.2")

        self.assertEqual(len(sent_rrep), 2)
        self.assertEqual(sent_rrep[0][0][0], "10.0.0.7")
        self.assertEqual(sent_rrep[1][1]["orig_addr"], "10.0.0.9")
        self.assertEqual(sent_rrep[1][1]["next_hop_ip"], "10.0.0.3")
        self.assertEqual(sent_rrep[1][1]["dest_addr"], "10.0.0.7")

    def test_rreq_join_is_ignored(self) -> None:
        protocol = self._new_protocol()
        sent_rrep: list[tuple] = []
        broadcasted: list[dict] = []
        protocol._send_rrep = lambda *args, **kwargs: sent_rrep.append((args, kwargs))
        protocol._broadcast_to_neighbors = lambda packet, exclude_node=None: broadcasted.append(dict(packet))

        packet = {
            "type": "RREQ",
            "sender": "10.0.0.2",
            "flags": RREQ_FLAG_JOIN,
            "hop_count": 1,
            "ttl": 6,
            "rreq_id": 13,
            "dest_addr": "10.0.0.9",
            "dest_seq_num": 1,
            "orig_addr": "10.0.0.7",
            "orig_seq_num": 5,
        }
        protocol._process_rreq(packet, sender_ip="10.0.0.2")

        self.assertEqual(len(sent_rrep), 0)
        self.assertEqual(len(broadcasted), 0)

    def test_rreq_unknown_seq_to_destination_does_not_trust_dest_seq(self) -> None:
        protocol = self._new_protocol()
        protocol.seq_num = 5
        sent_rrep: list[tuple] = []
        protocol._send_rrep = lambda *args, **kwargs: sent_rrep.append((args, kwargs))

        packet = {
            "type": "RREQ",
            "sender": "10.0.0.2",
            "flags": RREQ_FLAG_UNKNOWN_SEQ,
            "hop_count": 1,
            "ttl": 6,
            "rreq_id": 14,
            "dest_addr": "10.0.0.1",
            "dest_seq_num": 200,
            "orig_addr": "10.0.0.7",
            "orig_seq_num": 5,
        }
        protocol._process_rreq(packet, sender_ip="10.0.0.2")

        self.assertEqual(protocol.seq_num, 6)
        self.assertEqual(sent_rrep[0][0][3], 6)


if __name__ == "__main__":
    unittest.main()
