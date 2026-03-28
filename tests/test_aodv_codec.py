import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from aodv_codec import PROTOCOL_VERSION, RREQ_SUPPORTED_FLAG_MASK, decode_packet, encode_packet


class TestAodvCodec(unittest.TestCase):
    def test_rreq_codec_roundtrip(self) -> None:
        packet = {
            "type": "RREQ",
            "sender": "10.0.0.1",
            "flags": 0,
            "hop_count": 2,
            "ttl": 8,
            "rreq_id": 42,
            "dest_addr": "10.0.0.7",
            "dest_seq_num": 100,
            "orig_addr": "10.0.0.1",
            "orig_seq_num": 77,
        }
        raw = encode_packet(packet)
        out = decode_packet(raw)

        self.assertIsNotNone(out)
        self.assertEqual(out["type"], "RREQ")
        self.assertEqual(out["sender"], "10.0.0.1")
        self.assertEqual(out["dest_addr"], "10.0.0.7")
        self.assertEqual(out["rreq_id"], 42)

    def test_data_codec_roundtrip(self) -> None:
        packet = {
            "type": "DATA",
            "sender": "10.0.0.1",
            "orig_addr": "10.0.0.1",
            "dest_addr": "10.0.0.2",
            "hop_count": 0,
            "ttl": 16,
            "payload": "hello aodv",
        }
        raw = encode_packet(packet)
        out = decode_packet(raw)

        self.assertIsNotNone(out)
        self.assertEqual(out["type"], "DATA")
        self.assertEqual(out["payload"], "hello aodv")

    def test_rerr_codec_roundtrip(self) -> None:
        packet = {
            "type": "RERR",
            "sender": "10.0.0.9",
            "flags": 0,
            "unreachable": [
                {"dest_addr": "10.0.0.3", "dest_seq_num": 8},
                {"dest_addr": "10.0.0.4", "dest_seq_num": 11},
            ],
        }
        raw = encode_packet(packet)
        out = decode_packet(raw)

        self.assertIsNotNone(out)
        self.assertEqual(out["type"], "RERR")
        self.assertEqual(len(out["unreachable"]), 2)
        self.assertEqual(out["unreachable"][1]["dest_addr"], "10.0.0.4")

    def test_rrep_ack_codec_roundtrip(self) -> None:
        packet = {"type": "RREP-ACK", "sender": "10.0.0.5"}
        raw = encode_packet(packet)
        out = decode_packet(raw)

        self.assertIsNotNone(out)
        self.assertEqual(out["type"], "RREP-ACK")
        self.assertEqual(out["sender"], "10.0.0.5")

    def test_hello_over_rrep_roundtrip(self) -> None:
        packet = {
            "type": "RREP",
            "sender": "10.0.0.1",
            "flags": 0,
            "prefix_size": 0,
            "hop_count": 0,
            "ttl": 1,
            "dest_addr": "10.0.0.1",
            "dest_seq_num": 9,
            "orig_addr": "10.0.0.1",
            "lifetime": 20,
        }
        raw = encode_packet(packet)
        out = decode_packet(raw)

        self.assertIsNotNone(out)
        self.assertEqual(out["type"], "RREP")
        self.assertEqual(out["ttl"], 1)
        self.assertEqual(out["dest_addr"], "10.0.0.1")

    def test_decode_reject_bad_length(self) -> None:
        packet = {
            "type": "RREQ",
            "sender": "10.0.0.1",
            "flags": 0,
            "hop_count": 0,
            "ttl": 4,
            "rreq_id": 1,
            "dest_addr": "10.0.0.2",
            "dest_seq_num": 0,
            "orig_addr": "10.0.0.1",
            "orig_seq_num": 1,
        }
        raw = bytearray(encode_packet(packet))
        raw[3] = 0
        self.assertIsNone(decode_packet(bytes(raw)))

    def test_decode_reject_bad_version(self) -> None:
        packet = {
            "type": "RREP",
            "sender": "10.0.0.1",
            "flags": 0,
            "prefix_size": 0,
            "hop_count": 1,
            "ttl": 8,
            "dest_addr": "10.0.0.9",
            "dest_seq_num": 7,
            "orig_addr": "10.0.0.2",
            "lifetime": 100,
        }
        raw = bytearray(encode_packet(packet))
        raw[0] = (PROTOCOL_VERSION + 1) & 0xFF
        self.assertIsNone(decode_packet(bytes(raw)))

    def test_encode_reject_unsupported_rreq_flags(self) -> None:
        packet = {
            "type": "RREQ",
            "sender": "10.0.0.1",
            "flags": (RREQ_SUPPORTED_FLAG_MASK ^ 0xFF) & 0xFF,
            "hop_count": 0,
            "ttl": 4,
            "rreq_id": 1,
            "dest_addr": "10.0.0.2",
            "dest_seq_num": 0,
            "orig_addr": "10.0.0.1",
            "orig_seq_num": 1,
        }
        with self.assertRaises(ValueError):
            encode_packet(packet)


if __name__ == "__main__":
    unittest.main()
