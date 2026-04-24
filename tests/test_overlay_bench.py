import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from overlay_bench import compute_throughput_metrics


class TestOverlayBenchThroughputMetrics(unittest.TestCase):
    def test_goodput_uses_full_test_window_when_receiver_span_shrinks(self) -> None:
        baseline = compute_throughput_metrics(
            sent_packets=100,
            payload_size=1000,
            sender_duration_sec=1.0,
            report={
                "received_packets": 100,
                "received_bytes": 100_000,
                "duration_ns": 1_000_000_000,
            },
        )
        lossy = compute_throughput_metrics(
            sent_packets=100,
            payload_size=1000,
            sender_duration_sec=1.0,
            report={
                "received_packets": 70,
                "received_bytes": 70_000,
                "duration_ns": 500_000_000,
            },
        )

        self.assertEqual(lossy["measurement_duration_sec"], 1.0)
        self.assertLess(lossy["goodput_mbps"], baseline["goodput_mbps"])

    def test_goodput_respects_longer_receiver_observation_window(self) -> None:
        metrics = compute_throughput_metrics(
            sent_packets=100,
            payload_size=1000,
            sender_duration_sec=1.0,
            report={
                "received_packets": 100,
                "received_bytes": 100_000,
                "duration_ns": 1_500_000_000,
            },
        )

        self.assertEqual(metrics["receiver_duration_sec"], 1.5)
        self.assertEqual(metrics["measurement_duration_sec"], 1.5)
        self.assertAlmostEqual(metrics["offered_load_mbps"], 0.8, places=6)
        self.assertAlmostEqual(metrics["goodput_mbps"], 0.533333, places=6)


if __name__ == "__main__":
    unittest.main()
