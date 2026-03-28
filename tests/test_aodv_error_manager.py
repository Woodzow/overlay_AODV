import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from aodv_error_manager import ErrorManager


class TestErrorManager(unittest.TestCase):
    def test_normalize_unreachable_merge_and_limit(self) -> None:
        manager = ErrorManager()
        items = [
            {"dest_addr": "10.0.0.2", "dest_seq_num": 3},
            {"dest_addr": "10.0.0.2", "dest_seq_num": 7},
            {"dest_addr": "10.0.0.3", "dest_seq_num": 1},
        ]
        out = manager.normalize_unreachable(items, max_items=1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["dest_addr"], "10.0.0.2")
        self.assertEqual(out[0]["dest_seq_num"], 7)

    def test_rerr_rate_limit(self) -> None:
        manager = ErrorManager()
        items = [{"dest_addr": "10.0.0.2", "dest_seq_num": 7}]
        self.assertTrue(manager.should_emit_rerr(items, now=10.0, rate_limit_sec=2))
        self.assertFalse(manager.should_emit_rerr(items, now=11.0, rate_limit_sec=2))
        self.assertTrue(manager.should_emit_rerr(items, now=12.1, rate_limit_sec=2))

    def test_targets_for_unreachable(self) -> None:
        manager = ErrorManager()
        manager.add_precursor("10.0.0.9", "10.0.0.2")
        manager.add_precursor("10.0.0.9", "10.0.0.3")
        targets = manager.targets_for_unreachable([{"dest_addr": "10.0.0.9", "dest_seq_num": 1}])
        self.assertEqual(targets, {"10.0.0.2", "10.0.0.3"})


if __name__ == "__main__":
    unittest.main()
