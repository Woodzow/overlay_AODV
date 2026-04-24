import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from overlay_bench import ControlClient, OverlayBenchNode, compute_throughput_metrics


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


class TestOverlayBenchThroughputSessionFlush(unittest.TestCase):
    def test_end_packet_waits_for_settle_window_before_reporting(self) -> None:
        node = OverlayBenchNode(
            node_ip="10.0.0.2",
            data_port=0,
            control_client=ControlClient(),
            route_timeout_sec=1.0,
            route_poll_interval_sec=0.1,
            send_retries=0,
            send_retry_sleep_ms=0.0,
            socket_sndbuf_bytes=4096,
            socket_rcvbuf_bytes=4096,
            throughput_settle_ms=100.0,
            quiet=True,
        )
        reports: list[dict] = []
        node.send_overlay = reports.append  # type: ignore[method-assign]
        try:
            with patch("overlay_bench.time.perf_counter_ns", side_effect=[1_000_000_000]):
                node.handle_throughput_data(
                    {
                        "session_id": "s1",
                        "src_ip": "10.0.0.1",
                        "seq": 0,
                        "payload_size": 1000,
                    }
                )
            with patch("overlay_bench.time.perf_counter_ns", side_effect=[1_050_000_000, 1_060_000_000]):
                node.handle_throughput_end(
                    {
                        "session_id": "s1",
                        "src_ip": "10.0.0.1",
                        "expected_packets": 2,
                        "expected_bytes": 2000,
                    }
                )
            self.assertEqual(reports, [])

            with patch("overlay_bench.time.perf_counter_ns", side_effect=[1_090_000_000]):
                node.handle_throughput_data(
                    {
                        "session_id": "s1",
                        "src_ip": "10.0.0.1",
                        "seq": 1,
                        "payload_size": 1000,
                    }
                )
            with patch("overlay_bench.time.perf_counter_ns", side_effect=[1_091_000_000]):
                node.flush_throughput_sessions()
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]["received_packets"], 2)
            self.assertEqual(reports[0]["expected_packets"], 2)
        finally:
            node.close()


if __name__ == "__main__":
    unittest.main()
