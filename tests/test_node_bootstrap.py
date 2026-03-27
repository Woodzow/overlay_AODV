import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "Src"))

from node import build_node_config, parse_args


class TestNodeBootstrap(unittest.TestCase):
    def test_build_from_ip_defaults(self) -> None:
        args = parse_args(["--ip", "10.0.0.7", "--no-cli"])
        cfg = build_node_config(args)
        self.assertEqual(cfg.node_ip, "10.0.0.7")
        self.assertEqual(cfg.node_id, "n7")
        self.assertEqual(cfg.bind_ip, "0.0.0.0")
        self.assertEqual(cfg.overlay_port, 5005)
        self.assertEqual(cfg.control_bind_ip, "0.0.0.0")
        self.assertEqual(cfg.control_port, 5100)
        self.assertEqual(cfg.neighbors, [])

    def test_build_from_ip_with_overrides(self) -> None:
        args = parse_args(
            [
                "--ip",
                "10.0.0.8",
                "--node-id",
                "h8",
                "--overlay-port",
                "6000",
                "--control-port",
                "6200",
            ]
        )
        cfg = build_node_config(args)
        self.assertEqual(cfg.node_id, "h8")
        self.assertEqual(cfg.overlay_port, 6000)
        self.assertEqual(cfg.control_port, 6200)

    def test_parse_dest_ip(self) -> None:
        args = parse_args(["--ip", "10.0.0.9", "--dest-ip", "10.0.0.4"])
        self.assertEqual(args.dest_ip, "10.0.0.4")


if __name__ == "__main__":
    unittest.main()
