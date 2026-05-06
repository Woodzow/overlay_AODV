import csv
import unittest
from pathlib import Path

import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_FILE = REPO_ROOT / "tools" / "mininet_wifi_complex_12sta_loss_sweep_table.py"


def load_table_module():
    spec = importlib.util.spec_from_file_location("loss_sweep_table_tool", SCRIPT_FILE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LossSweepTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_table_module()

    def test_compact_rows_match_report_columns(self) -> None:
        rows = self.module.compact_rows(
            [
                {
                    "tc_loss_percent": 0,
                    "hop_count": 3,
                    "loss_rate": 0.0,
                    "goodput_mbps": 4.428,
                    "offered_load_mbps": 4.9,
                },
                {
                    "tc_loss_percent": 5,
                    "hop_count": 3,
                    "loss_rate": 0.141,
                    "goodput_mbps": 3.436,
                },
            ]
        )

        self.assertEqual(
            [
                {"tc_loss%": "0", "hop": "3", "loss_rate": "0", "goodput_mbps": "4.428"},
                {"tc_loss%": "5", "hop": "3", "loss_rate": "0.141", "goodput_mbps": "3.436"},
            ],
            rows,
        )

    def test_markdown_table_uses_excel_friendly_headers(self) -> None:
        table = self.module.format_markdown_table(
            [{"tc_loss%": "1", "hop": "3", "loss_rate": "0.026", "goodput_mbps": "4.276"}]
        )

        self.assertIn("| tc_loss% | hop | loss_rate | goodput_mbps |", table)
        self.assertIn("| 1 | 3 | 0.026 | 4.276 |", table)

    def test_write_csv_uses_same_column_order(self) -> None:
        rows = [{"tc_loss%": "2", "hop": "3", "loss_rate": "0.056", "goodput_mbps": "4.042"}]
        output_path = REPO_ROOT / "tests" / "_loss_sweep_table_output.csv"
        try:
            if output_path.exists():
                output_path.unlink()
            self.module.write_csv(output_path, rows)

            with output_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                self.assertEqual(
                    [
                        ["tc_loss%", "hop", "loss_rate", "goodput_mbps"],
                        ["2", "3", "0.056", "4.042"],
                    ],
                    list(reader),
                )
        finally:
            if output_path.exists():
                output_path.unlink()


if __name__ == "__main__":
    unittest.main()
