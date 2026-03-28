import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from aodv_duplicate_set import DuplicateSet
from aodv_models import RouteEntry
from aodv_route_manager import RouteManager
from aodv_sequence import is_seq_newer


class TestSequenceAndRouteManager(unittest.TestCase):
    def test_seq_wraparound_newer(self) -> None:
        self.assertTrue(is_seq_newer(0, 0xFFFFFFFF))
        self.assertTrue(is_seq_newer(10, 1))
        self.assertFalse(is_seq_newer(1, 10))
        self.assertFalse(is_seq_newer(100, 100))

    def test_route_replace_on_newer_seq(self) -> None:
        table: dict[str, RouteEntry] = {}
        manager = RouteManager(table)

        old = RouteEntry(
            dest_addr="10.0.0.8",
            next_hop="10.0.0.2",
            next_hop_ip="10.0.0.2",
            hop_count=3,
            dest_seq_num=20,
            valid=True,
            route_state="VALID",
            expires_at=100.0,
        )
        manager.upsert_discovered(old)

        new = RouteEntry(
            dest_addr="10.0.0.8",
            next_hop="10.0.0.3",
            next_hop_ip="10.0.0.3",
            hop_count=5,
            dest_seq_num=21,
            valid=True,
            route_state="VALID",
            expires_at=150.0,
        )
        manager.upsert_discovered(new)

        self.assertEqual(table["10.0.0.8"].next_hop_ip, "10.0.0.3")
        self.assertEqual(table["10.0.0.8"].dest_seq_num, 21)

    def test_route_replace_on_shorter_hop_same_seq(self) -> None:
        table: dict[str, RouteEntry] = {}
        manager = RouteManager(table)

        old = RouteEntry(
            dest_addr="10.0.0.9",
            next_hop="10.0.0.2",
            next_hop_ip="10.0.0.2",
            hop_count=5,
            dest_seq_num=30,
            valid=True,
            route_state="VALID",
            expires_at=200.0,
        )
        manager.upsert_discovered(old)

        shorter = RouteEntry(
            dest_addr="10.0.0.9",
            next_hop="10.0.0.4",
            next_hop_ip="10.0.0.4",
            hop_count=2,
            dest_seq_num=30,
            valid=True,
            route_state="VALID",
            expires_at=210.0,
        )
        manager.upsert_discovered(shorter)

        self.assertEqual(table["10.0.0.9"].hop_count, 2)
        self.assertEqual(table["10.0.0.9"].next_hop_ip, "10.0.0.4")

    def test_duplicate_set_lifecycle(self) -> None:
        dset = DuplicateSet()
        key = ("10.0.0.1", 77)

        dset.remember(key, expires_at=10.0)
        self.assertTrue(dset.has_valid(key, now=5.0))
        self.assertFalse(dset.was_retransmitted(key))

        dset.mark_retransmitted(key)
        self.assertTrue(dset.was_retransmitted(key))

        dset.cleanup(now=11.0)
        self.assertFalse(dset.has_valid(key, now=11.0))

    def test_mark_local_repairing_invalidates_temp(self) -> None:
        table: dict[str, RouteEntry] = {}
        manager = RouteManager(table)
        manager.upsert_connected("10.0.0.8", "10.0.0.2", now=1.0, lifetime_sec=60)
        route = manager.mark_local_repairing("10.0.0.8", now=2.0, wait_sec=5)
        self.assertIsNotNone(route)
        self.assertEqual(route.route_state, "REPAIRING")
        self.assertIsNone(manager.get_valid("10.0.0.8", now=2.5))


if __name__ == "__main__":
    unittest.main()
