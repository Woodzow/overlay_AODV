import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "Src"))

from aodv_ack_manager import RrepAckManager


class TestRrepAckManager(unittest.TestCase):
    def test_track_and_ack(self) -> None:
        manager = RrepAckManager()
        manager.track("10.0.0.2", now=1.0, timeout_sec=2)
        self.assertTrue(manager.acknowledge("10.0.0.2"))
        self.assertFalse(manager.acknowledge("10.0.0.2"))

    def test_timeout_neighbors(self) -> None:
        manager = RrepAckManager()
        manager.track("10.0.0.2", now=1.0, timeout_sec=2)
        manager.track("10.0.0.3", now=1.0, timeout_sec=5)
        timed_out = manager.timed_out_neighbors(now=3.2)
        self.assertIn("10.0.0.2", timed_out)
        self.assertNotIn("10.0.0.3", timed_out)


if __name__ == "__main__":
    unittest.main()
