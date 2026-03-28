import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from aodv_local_repair_manager import LocalRepairManager


class TestLocalRepairManager(unittest.TestCase):
    def test_start_and_complete(self) -> None:
        manager = LocalRepairManager()
        manager.start("10.0.0.8", dest_seq_num=12, now=1.0, wait_sec=5)
        self.assertTrue(manager.is_repairing("10.0.0.8"))
        manager.complete("10.0.0.8")
        self.assertFalse(manager.is_repairing("10.0.0.8"))

    def test_timeout(self) -> None:
        manager = LocalRepairManager()
        manager.start("10.0.0.9", dest_seq_num=21, now=1.0, wait_sec=3)
        timed_out = manager.timed_out(now=4.5)
        self.assertEqual(len(timed_out), 1)
        self.assertEqual(timed_out[0].dest_addr, "10.0.0.9")
        self.assertFalse(manager.is_repairing("10.0.0.9"))


if __name__ == "__main__":
    unittest.main()
