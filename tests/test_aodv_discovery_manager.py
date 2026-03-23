import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "Src"))

from aodv_discovery_manager import DiscoveryManager


class TestDiscoveryManager(unittest.TestCase):
    def test_first_send_allowed(self) -> None:
        manager = DiscoveryManager()
        self.assertTrue(manager.should_send("10.0.0.8", now=1.0, max_retries=3))

    def test_ttl_expanding_ring(self) -> None:
        manager = DiscoveryManager()
        ttl = manager.current_ttl("10.0.0.8", ttl_start=2, ttl_increment=2, ttl_threshold=7, max_ttl=16)
        self.assertEqual(ttl, 2)
        manager.mark_sent("10.0.0.8", ttl_used=ttl, now=1.0, retry_wait_sec=2)

        ttl = manager.current_ttl("10.0.0.8", ttl_start=2, ttl_increment=2, ttl_threshold=7, max_ttl=16)
        self.assertEqual(ttl, 4)
        manager.mark_sent("10.0.0.8", ttl_used=ttl, now=4.0, retry_wait_sec=2)

        ttl = manager.current_ttl("10.0.0.8", ttl_start=2, ttl_increment=2, ttl_threshold=7, max_ttl=16)
        self.assertEqual(ttl, 6)

    def test_retry_and_exhausted(self) -> None:
        manager = DiscoveryManager()
        manager.mark_sent("10.0.0.8", ttl_used=2, now=1.0, retry_wait_sec=2)
        self.assertFalse(manager.should_send("10.0.0.8", now=2.0, max_retries=3))
        self.assertTrue(manager.should_send("10.0.0.8", now=3.1, max_retries=3))

        manager.mark_sent("10.0.0.8", ttl_used=4, now=3.1, retry_wait_sec=2)
        manager.mark_sent("10.0.0.8", ttl_used=6, now=5.2, retry_wait_sec=2)
        self.assertIn("10.0.0.8", manager.exhausted_destinations(max_retries=3))

    def test_clear_state(self) -> None:
        manager = DiscoveryManager()
        manager.mark_sent("10.0.0.9", ttl_used=2, now=1.0, retry_wait_sec=2)
        manager.clear("10.0.0.9")
        self.assertNotIn("10.0.0.9", manager.snapshot())


if __name__ == "__main__":
    unittest.main()
