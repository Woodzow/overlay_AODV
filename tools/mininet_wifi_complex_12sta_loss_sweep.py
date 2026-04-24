#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from pathlib import Path

from mininet.log import info, setLogLevel
from mn_wifi.link import adhoc, wmediumd
from mn_wifi.net import Mininet_wifi
from mn_wifi.wmediumdConnector import interference

try:
    from mn_wifi.cli import CLI
except ImportError:
    from mn_wifi.cli import CLI_wifi as CLI


TOPOLOGY_FILE = Path(__file__).resolve().parents[1] / "configs" / "mininet_wifi_complex_12sta" / "topology.json"
DEFAULT_OUTPUT_JSON = Path("logs") / "mininet_wifi_complex_12sta_loss_sweep" / "results.json"


def load_topology() -> dict:
    return json.loads(TOPOLOGY_FILE.read_text(encoding="utf-8"))


def parse_args(topology: dict) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-click loss sweep on the 12-station complex Mininet-WiFi topology. Applies tc netem loss from 1% to 10% and measures sta1->sta12 overlay throughput and loss."
    )
    parser.add_argument(
        "--neighbor-wait-sec",
        type=float,
        default=4.0,
        help="Time to wait after AODV startup before each measurement round.",
    )
    parser.add_argument(
        "--aodv-startup-sec",
        type=float,
        default=2.0,
        help="Extra wait after starting AODV processes before the neighbor wait begins.",
    )
    parser.add_argument(
        "--daemon-startup-sec",
        type=float,
        default=1.0,
        help="Time to wait after starting overlay_bench daemons before the sender starts throughput measurement.",
    )
    parser.add_argument(
        "--round-stop-sec",
        type=float,
        default=1.0,
        help="Time to wait after stopping AODV and bench daemons before the next loss round.",
    )
    parser.add_argument(
        "--min-loss",
        type=int,
        default=1,
        help="Minimum tc netem loss percentage to test.",
    )
    parser.add_argument(
        "--max-loss",
        type=int,
        default=10,
        help="Maximum tc netem loss percentage to test.",
    )
    parser.add_argument(
        "--loss-step",
        type=int,
        default=1,
        help="Step between tested tc netem loss percentages.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="Number of overlay throughput packets per loss round.",
    )
    parser.add_argument(
        "--payload-size",
        type=int,
        default=1000,
        help="Payload size in bytes per overlay throughput packet.",
    )
    parser.add_argument(
        "--interval-ms",
        type=float,
        default=1.0,
        help="Delay between packets in milliseconds. Defaults to 1ms for a paced throughput stream; 0 means send as fast as possible.",
    )
    parser.add_argument(
        "--route-timeout-sec",
        type=float,
        default=12.0,
        help="Max time to wait for AODV route establishment in overlay_bench throughput mode.",
    )
    parser.add_argument(
        "--route-poll-interval-sec",
        type=float,
        default=0.2,
        help="Polling interval while waiting for routes in overlay_bench throughput mode.",
    )
    parser.add_argument(
        "--report-timeout-sec",
        type=float,
        default=15.0,
        help="Timeout waiting for the throughput report from the destination.",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_JSON),
        help="Path to save aggregate sweep results as JSON. Relative paths are resolved from the repo root.",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Restart the topology after the sweep and drop into the Mininet-WiFi CLI.",
    )
    parser.add_argument(
        "--source",
        default=topology.get("video_source", "sta1"),
        help="Source station name. Default follows the topology file.",
    )
    parser.add_argument(
        "--dest",
        default=topology.get("video_dest", "sta12"),
        help="Destination station name. Default follows the topology file.",
    )
    return parser.parse_args()


def run_cmd(node, command: str) -> str:
    return node.cmd(command).strip()


def ip_without_mask(ip_text: str) -> str:
    return str(ip_text).split("/", 1)[0]


def source_ip_of(topology: dict, station_name: str) -> str:
    for item in topology["stations"]:
        if item["name"] == station_name:
            return ip_without_mask(item["ip"])
    raise KeyError(f"unknown station in topology: {station_name}")


def build_topology(topology: dict):
    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference)
    radio_range = float(topology["radio_range"])

    stations = []
    for item in topology["stations"]:
        station = net.addStation(
            item["name"],
            ip=item["ip"],
            position=f"{item['x']},{item['y']},0",
            range=radio_range,
        )
        stations.append(station)

    net.setPropagationModel(
        model=topology.get("propagation_model", "logDistance"),
        exp=float(topology.get("propagation_exp", 4.0)),
    )
    net.configureWifiNodes()

    for sta in stations:
        net.addLink(
            sta,
            cls=adhoc,
            intf=f"{sta.name}-wlan0",
            ssid=topology.get("ssid", "aodv-adhoc"),
            mode=topology.get("mode", "g"),
            channel=int(topology.get("channel", 1)),
        )

    return net, tuple(stations)


def start_aodv(node, config_path: Path, repo_root: Path, log_dir: Path) -> None:
    repo_text = shlex.quote(str(repo_root))
    src_text = shlex.quote(str(repo_root / "src"))
    cfg_text = shlex.quote(str(config_path))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_text = shlex.quote(str(log_dir / f"{node.name}-aodv.out"))
    cmd = (
        f"cd {repo_text} && "
        f"PYTHONPATH={src_text} "
        f"nohup python3 src/main.py node --config {cfg_text} > {log_text} 2>&1 &"
    )
    node.cmd(cmd)


def stop_aodv(node) -> None:
    node.cmd("pkill -f 'src/main.py node --config' >/dev/null 2>&1 || true")


def start_bench_daemon(node, node_ip: str, repo_root: Path, log_dir: Path) -> None:
    repo_text = shlex.quote(str(repo_root))
    src_text = shlex.quote(str(repo_root / "src"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_text = shlex.quote(str(log_dir / f"{node.name}-bench.log"))
    cmd = (
        f"cd {repo_text} && "
        f"PYTHONPATH={src_text} "
        f"nohup python3 src/overlay_bench.py daemon --node-ip {node_ip} --quiet --log-file {log_text} "
        "> /dev/null 2>&1 &"
    )
    node.cmd(cmd)


def stop_bench_daemon(node) -> None:
    node.cmd("pkill -f 'overlay_bench.py daemon' >/dev/null 2>&1 || true")


def stop_round_processes(stations) -> None:
    for sta in stations:
        stop_bench_daemon(sta)
    for sta in stations:
        stop_aodv(sta)


def apply_link_loss(stations, loss_percent: float) -> None:
    info(f"*** Applying tc netem loss={loss_percent:.2f}% on all station wlan interfaces\n")
    for sta in stations:
        intf = f"{sta.name}-wlan0"
        sta.cmd(f"tc qdisc replace dev {intf} root netem loss {loss_percent:.2f}%")
        qdisc_state = run_cmd(sta, f"tc qdisc show dev {intf}")
        info(f"[{sta.name}] {qdisc_state}\n")


def clear_link_loss(stations) -> None:
    for sta in stations:
        intf = f"{sta.name}-wlan0"
        sta.cmd(f"tc qdisc del dev {intf} root >/dev/null 2>&1 || true")


def extract_json_result(text: str) -> dict:
    for line in reversed([item.strip() for item in text.splitlines() if item.strip()]):
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise ValueError(f"benchmark output did not contain a JSON object: {text}")


def run_throughput_measurement(
    source_node,
    source_ip: str,
    dest_ip: str,
    repo_root: Path,
    args: argparse.Namespace,
) -> dict:
    command = (
        f"cd {shlex.quote(str(repo_root))} && "
        f"PYTHONPATH={shlex.quote(str(repo_root / 'src'))} "
        "python3 src/overlay_bench.py throughput "
        f"--node-ip {source_ip} "
        f"--dest-ip {dest_ip} "
        f"--count {int(args.count)} "
        f"--payload-size {int(args.payload_size)} "
        f"--interval-ms {float(args.interval_ms)} "
        f"--route-timeout-sec {float(args.route_timeout_sec)} "
        f"--route-poll-interval-sec {float(args.route_poll_interval_sec)} "
        f"--report-timeout-sec {float(args.report_timeout_sec)} "
        "--quiet --json"
    )
    return extract_json_result(run_cmd(source_node, command))


def print_results(results: list[dict], source_name: str, dest_name: str) -> None:
    info(f"\n=== overlay throughput/loss sweep ({source_name} -> {dest_name}) ===\n")
    info("tc_loss%  status        hop  route_setup_sec  overlay_loss_rate  pdr         goodput_mbps  offered_load_mbps\n")
    info("-----------------------------------------------------------------------------------------------------------\n")
    for item in results:
        route_setup_text = str(item.get("route_setup_sec", "-"))
        hop_text = str(item.get("hop_count", "-"))
        loss_rate_text = str(item.get("loss_rate", "-"))
        pdr_text = str(item.get("pdr", "-"))
        goodput_text = str(item.get("goodput_mbps", "-"))
        offered_text = str(item.get("offered_load_mbps", "-"))
        info(
            f"{item['tc_loss_percent']:<8} {item['status']:<13} {hop_text:<4} {route_setup_text:<16} "
            f"{loss_rate_text:<18} {pdr_text:<11} {goodput_text:<13} {offered_text}\n"
        )
    info("\njson=" + json.dumps(results, ensure_ascii=True, separators=(",", ":")) + "\n")


def resolve_output_path(repo_root: Path, output_json: str) -> Path:
    path = Path(output_json)
    if not path.is_absolute():
        path = repo_root / path
    return path


def validate_args(args: argparse.Namespace, topology: dict) -> None:
    if args.min_loss < 0 or args.max_loss < 0:
        raise ValueError("loss percentages must be non-negative")
    if args.min_loss > args.max_loss:
        raise ValueError("--min-loss must be less than or equal to --max-loss")
    if args.loss_step <= 0:
        raise ValueError("--loss-step must be greater than zero")

    station_names = {item["name"] for item in topology["stations"]}
    if args.source not in station_names:
        raise ValueError(f"unknown source station: {args.source}")
    if args.dest not in station_names:
        raise ValueError(f"unknown destination station: {args.dest}")
    if args.source == args.dest:
        raise ValueError("source and destination must be different stations")


def loss_values(args: argparse.Namespace) -> list[int]:
    return list(range(args.min_loss, args.max_loss + 1, args.loss_step))


def main() -> int:
    topology = load_topology()
    args = parse_args(topology)

    try:
        validate_args(args, topology)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if os.geteuid() != 0:
        print("This script must be run with sudo/root.", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    config_dir = repo_root / "configs" / "mininet_wifi_complex_12sta"
    config_map = {
        item["name"]: config_dir / f"{item['name']}.json"
        for item in topology["stations"]
    }

    missing = [str(path) for path in config_map.values() if not path.exists()]
    if missing:
        print("Missing config files:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 1

    source_ip = source_ip_of(topology, args.source)
    dest_ip = source_ip_of(topology, args.dest)
    round_losses = loss_values(args)
    output_path = resolve_output_path(repo_root, args.output_json)
    root_log_dir = output_path.parent

    net, stations = build_topology(topology)
    stations_by_name = {node.name: node for node in stations}
    source_node = stations_by_name[args.source]

    results: list[dict] = []
    has_failure = False

    try:
        info("*** Building Mininet-WiFi network\n")
        net.build()

        for loss_percent in round_losses:
            round_log_dir = root_log_dir / f"loss_{loss_percent:02d}"
            info(
                f"\n*** Measuring overlay throughput under tc netem loss={loss_percent}% "
                f"({args.source} -> {args.dest}, {source_ip} -> {dest_ip})\n"
            )

            stop_round_processes(stations)
            clear_link_loss(stations)
            time.sleep(float(args.round_stop_sec))

            apply_link_loss(stations, float(loss_percent))

            for sta in stations:
                start_aodv(sta, config_map[sta.name], repo_root, round_log_dir)
            time.sleep(float(args.aodv_startup_sec))
            info(f"*** Waiting {args.neighbor_wait_sec:.1f}s before starting bench daemons\n")
            time.sleep(float(args.neighbor_wait_sec))

            for sta in stations:
                if sta.name == args.source:
                    continue
                start_bench_daemon(sta, source_ip_of(topology, sta.name), repo_root, round_log_dir)
            time.sleep(float(args.daemon_startup_sec))

            result = {
                "tc_loss_percent": loss_percent,
                "source": args.source,
                "source_ip": source_ip,
                "destination": args.dest,
                "dest_ip": dest_ip,
                "status": "ok",
            }
            try:
                measure = run_throughput_measurement(
                    source_node=source_node,
                    source_ip=source_ip,
                    dest_ip=dest_ip,
                    repo_root=repo_root,
                    args=args,
                )
                result.update(measure)
            except Exception as exc:
                result["status"] = "error"
                result["error"] = str(exc)
                has_failure = True
            finally:
                results.append(result)
                round_log_dir.mkdir(parents=True, exist_ok=True)
                (round_log_dir / "result.json").write_text(
                    json.dumps(result, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                stop_round_processes(stations)
                time.sleep(float(args.round_stop_sec))

        print_results(results, args.source, args.dest)

        root_log_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        info(f"*** Wrote aggregate JSON results to {output_path}\n")

        if args.cli:
            info("\n*** Clearing qdisc and restarting the topology for Mininet-WiFi CLI\n")
            clear_link_loss(stations)
            for sta in stations:
                start_aodv(sta, config_map[sta.name], repo_root, root_log_dir / "cli")
            time.sleep(float(args.aodv_startup_sec))
            for sta in stations:
                if sta.name == args.source:
                    continue
                start_bench_daemon(sta, source_ip_of(topology, sta.name), repo_root, root_log_dir / "cli")
            time.sleep(float(args.daemon_startup_sec))
            CLI(net)

        return 1 if has_failure else 0
    finally:
        stop_round_processes(stations)
        clear_link_loss(stations)
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    raise SystemExit(main())
