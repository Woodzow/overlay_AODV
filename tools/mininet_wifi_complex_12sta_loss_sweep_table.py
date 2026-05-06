#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_INPUT_JSON = Path("logs") / "mininet_wifi_complex_12sta_loss_sweep" / "results.json"
DEFAULT_OUTPUT_CSV = Path("logs") / "mininet_wifi_complex_12sta_loss_sweep" / "results_table.csv"
COLUMNS = ("tc_loss%", "hop", "loss_rate", "goodput_mbps")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Format the 12-station loss sweep JSON into a compact throughput/loss table."
    )
    parser.add_argument(
        "--input-json",
        default=str(DEFAULT_INPUT_JSON),
        help="Path to the sweep results.json file.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(DEFAULT_OUTPUT_CSV),
        help="Path to write the compact CSV table. Use '-' to skip writing CSV.",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=3,
        help="Decimal places for loss_rate and goodput_mbps.",
    )
    return parser.parse_args()


def resolve_repo_path(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = repo_root / path
    return path


def load_results(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    raise ValueError(f"unsupported sweep result JSON shape: {path}")


def format_number(value: Any, precision: int) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = f"{value:.{precision}f}"
        return text.rstrip("0").rstrip(".") if "." in text else text
    return str(value)


def compact_rows(results: list[dict[str, Any]], precision: int = 3) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in results:
        rows.append(
            {
                "tc_loss%": format_number(item.get("tc_loss_percent"), 0),
                "hop": format_number(item.get("hop_count"), 0),
                "loss_rate": format_number(item.get("loss_rate"), precision),
                "goodput_mbps": format_number(item.get("goodput_mbps"), precision),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def format_markdown_table(rows: list[dict[str, str]]) -> str:
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "| " + " | ".join("---" for _ in COLUMNS) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row[column] for column in COLUMNS) + " |")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    input_path = resolve_repo_path(args.input_json, repo_root)

    try:
        rows = compact_rows(load_results(input_path), precision=args.precision)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(format_markdown_table(rows))

    if args.output_csv != "-":
        output_path = resolve_repo_path(args.output_csv, repo_root)
        write_csv(output_path, rows)
        print(f"\ncsv={output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
