import sys
import time
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "Src"))

from aodv_config import NodeConfig
from aodv_protocol import AodvProtocol


class TestAodvProtocolBuffering(unittest.TestCase):
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

    def test_source_packet_buffer_and_flush(self) -> None:
        protocol = self._new_protocol()
        discoveries: list[tuple[str, int, bool]] = []
        sent: list[tuple[str, dict]] = []

        protocol._start_route_discovery = lambda dest, seq=0, force=False: discoveries.append((dest, seq, force))
        protocol._send_packet_to_ip = lambda ip, packet: sent.append((ip, dict(packet)))

        result = protocol._send_user_data("10.0.0.9", "hello")
        self.assertIn("已触发发现", result)
        self.assertIn("10.0.0.9", protocol.pending_data_packets)
        self.assertEqual(len(protocol.pending_data_packets["10.0.0.9"]), 1)
        self.assertEqual(discoveries[0][0], "10.0.0.9")

        now = time.time()
        protocol.route_manager.upsert_connected("10.0.0.9", "10.0.0.2", now=now, lifetime_sec=60)
        protocol._flush_pending_data("10.0.0.9")

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "10.0.0.2")
        self.assertEqual(sent[0][1]["orig_addr"], "10.0.0.1")
        self.assertEqual(sent[0][1]["hop_count"], 0)

    def test_forward_packet_buffer_keeps_orig_and_increments_once(self) -> None:
        protocol = self._new_protocol()
        discoveries: list[tuple[str, int, bool]] = []
        sent: list[tuple[str, dict]] = []

        protocol._start_route_discovery = lambda dest, seq=0, force=False: discoveries.append((dest, seq, force))
        protocol._send_packet_to_ip = lambda ip, packet: sent.append((ip, dict(packet)))

        incoming = {
            "type": "DATA",
            "sender": "10.0.0.2",
            "orig_addr": "10.0.0.7",
            "dest_addr": "10.0.0.9",
            "hop_count": 1,
            "ttl": 6,
            "payload": "x",
        }
        protocol._process_data(incoming, sender_ip="10.0.0.2")

        self.assertEqual(discoveries[0][0], "10.0.0.9")
        self.assertEqual(len(protocol.pending_data_packets["10.0.0.9"]), 1)
        buffered = protocol.pending_data_packets["10.0.0.9"][0]
        self.assertEqual(buffered["orig_addr"], "10.0.0.7")
        self.assertEqual(buffered["sender"], "10.0.0.1")
        self.assertEqual(buffered["hop_count"], 2)
        self.assertEqual(buffered["ttl"], 5)

        now = time.time()
        protocol.route_manager.upsert_connected("10.0.0.9", "10.0.0.3", now=now, lifetime_sec=60)
        protocol._flush_pending_data("10.0.0.9")

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "10.0.0.3")
        self.assertEqual(sent[0][1]["orig_addr"], "10.0.0.7")
        self.assertEqual(sent[0][1]["hop_count"], 2)
        self.assertEqual(sent[0][1]["ttl"], 5)


if __name__ == "__main__":
    unittest.main()
