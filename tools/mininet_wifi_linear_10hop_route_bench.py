#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
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


TOPOLOGY_FILE = Path(__file__).resolve().parents[1] / "configs" / "mininet_wifi_linear_10hop" / "topology.json"
BASE_CONFIG_FILE = Path(__file__).resolve().parents[1] / "configs" / "mininet_wifi_linear_10hop" / "base_config.json"


def load_topology() -> dict:
    return json.loads(TOPOLOGY_FILE.read_text(encoding="utf-8"))


def load_base_config() -> dict:
    return json.loads(BASE_CONFIG_FILE.read_text(encoding="utf-8-sig"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an 11-station linear Mininet-WiFi topology and measure AODV route discovery time for 1-8 hops by default."
    )
    parser.add_argument(
        "--neighbor-wait-sec",
        type=float,
        default=4.0,
        help="Time to wait after AODV startup before running one route measurement round.",
    )
    parser.add_argument(
        "--aodv-startup-sec",
        type=float,
        default=2.0,
        help="Extra wait after starting AODV processes before the neighbor wait begins.",
    )
    parser.add_argument(
        "--round-stop-sec",
        type=float,
        default=1.0,
        help="Time to wait after stopping AODV processes before starting the next hop round.",
    )
    parser.add_argument(
        "--route-timeout-sec",
        type=float,
        default=12.0,
        help="Max time to wait for a route to converge in each benchmark round.",
    )
    parser.add_argument(
        "--route-poll-interval-sec",
        type=float,
        default=0.2,
        help="Polling interval used by overlay_bench.py while waiting for route convergence.",
    )
    parser.add_argument(
        "--output-json",
        help="Optional path to save the aggregate benchmark result as JSON.",
    )
    parser.add_argument(
        "--max-hop",
        type=int,
        default=8,
        help="Max hop count to measure from sta1. Default is 8. The current topology supports up to 10.",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="After all measurements finish, restart AODV once and drop into the Mininet-WiFi CLI.",
    )
    return parser.parse_args()


def run_cmd(node, command: str) -> str:
    return node.cmd(command).strip()


def start_aodv(node, config_path: Path, repo_root: Path) -> None:
    repo_text = shlex.quote(str(repo_root))
    src_text = shlex.quote(str(repo_root / "src"))
    cfg_text = shlex.quote(str(config_path))
    log_dir = repo_root / "logs" / "mininet_wifi_linear_10hop"
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


def ip_without_mask(ip_text: str) -> str:
    return str(ip_text).split("/", 1)[0]


def source_ip_of(topology: dict, station_name: str) -> str:
    for item in topology["stations"]:
        if item["name"] == station_name:
            return ip_without_mask(item["ip"])
    raise KeyError(f"unknown station: {station_name}")


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


def prepare_runtime_configs(repo_root: Path, topology: dict) -> dict[str, Path]:
    base_config = load_base_config()
    station_map = {item["name"]: item for item in topology["stations"]}
    runtime_dir = repo_root / "logs" / "mininet_wifi_linear_10hop" / "runtime_configs"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    config_map: dict[str, Path] = {}
    for station_name, station in station_map.items():
        config = copy.deepcopy(base_config)
        config["node_id"] = station_name
        config["node_ip"] = ip_without_mask(station["ip"])
        config["neighbors"] = [
            {
                "node_id": neighbor_name,
                "ip": ip_without_mask(station_map[neighbor_name]["ip"]),
            }
            for neighbor_name in topology["edges"][station_name]
        ]
        config_path = runtime_dir / f"{station_name}.json"
        config_path.write_text(json.dumps(config, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        config_map[station_name] = config_path
    return config_map


def extract_json_result(text: str) -> dict:
    for line in reversed([item.strip() for item in text.splitlines() if item.strip()]):
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise ValueError(f"benchmark output did not contain a JSON object: {text}")


def measure_one_hop(
    source_node,
    source_ip: str,
    dest_ip: str,
    repo_root: Path,
    route_timeout_sec: float,
    route_poll_interval_sec: float,
) -> dict:
    command = (
        f"cd {shlex.quote(str(repo_root))} && "
        f"PYTHONPATH={shlex.quote(str(repo_root / 'src'))} "
        f"python3 src/overlay_bench.py route "
        f"--node-ip {source_ip} "
        f"--dest-ip {dest_ip} "
        f"--route-timeout-sec {float(route_timeout_sec)} "
        f"--route-poll-interval-sec {float(route_poll_interval_sec)} "
        "--quiet --json"
    )
    return extract_json_result(run_cmd(source_node, command))


def print_results(results: list[dict], max_hop: int) -> None:
    info(f"\n=== AODV route discovery time (1-{max_hop} hops) ===\n")
    info("hop  destination  measured_hop  route_setup_sec  next_hop_ip      status\n")
    info("-------------------------------------------------------------------------\n")
    for item in results:
        hop_text = str(item["hop"])
        dest_text = item["destination"]
        measured_hop_text = str(item.get("hop_count", "-"))
        route_time_text = f"{item.get('route_setup_sec', '-')}"
        next_hop_text = item.get("next_hop_ip", "-")
        status_text = item["status"]
        info(
            f"{hop_text:<4} {dest_text:<12} {measured_hop_text:<13} {route_time_text:<16} "
            f"{next_hop_text:<16} {status_text}\n"
        )

    info("\njson=" + json.dumps(results, ensure_ascii=True, separators=(",", ":")) + "\n")


def main() -> int:
    args = parse_args()
    topology = load_topology()
    topology_max_hop = len(topology["stations"]) - 1

    if args.max_hop < 1 or args.max_hop > topology_max_hop:
        print(
            f"--max-hop must be between 1 and {topology_max_hop} for the current topology.",
            file=sys.stderr,
        )
        return 1

    if os.geteuid() != 0:
        print("This script must be run with sudo/root.", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    config_map = prepare_runtime_configs(repo_root, topology)
    net, stations = build_topology(topology)
    stations_by_name = {node.name: node for node in stations}
    source_name = topology["route_source"]
    source_node = stations_by_name[source_name]
    source_ip = source_ip_of(topology, source_name)

    results: list[dict] = []
    has_failure = False

    try:
        info("*** Building Mininet-WiFi network\n")
        net.build()

        for hop in range(1, args.max_hop + 1):
            dest_name = f"sta{hop + 1}"
            dest_ip = source_ip_of(topology, dest_name)

            info(f"\n*** Measuring route discovery time for hop={hop} ({source_name} -> {dest_name}, {dest_ip})\n")
            for sta in stations:
                stop_aodv(sta)
            time.sleep(float(args.round_stop_sec))

            for sta in stations:
                start_aodv(sta, config_map[sta.name], repo_root)

            time.sleep(float(args.aodv_startup_sec))
            info(f"*** Waiting {args.neighbor_wait_sec:.1f}s before measurement\n")
            time.sleep(float(args.neighbor_wait_sec))

            result = {
                "hop": hop,
                "destination": dest_name,
                "dest_ip": dest_ip,
                "status": "ok",
            }
            try:
                measure = measure_one_hop(
                    source_node=source_node,
                    source_ip=source_ip,
                    dest_ip=dest_ip,
                    repo_root=repo_root,
                    route_timeout_sec=args.route_timeout_sec,
                    route_poll_interval_sec=args.route_poll_interval_sec,
                )
                result.update(measure)
                if int(measure.get("hop_count", -1)) != hop:
                    result["status"] = "hop_mismatch"
                    has_failure = True
            except Exception as exc:
                result["status"] = "error"
                result["error"] = str(exc)
                has_failure = True
            finally:
                results.append(result)
                for sta in stations:
                    stop_aodv(sta)
                time.sleep(float(args.round_stop_sec))

        print_results(results, args.max_hop)

        if args.output_json:
            output_path = Path(args.output_json)
            if not output_path.is_absolute():
                output_path = repo_root / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(results, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
            info(f"*** Wrote JSON results to {output_path}\n")

        if args.cli:
            info("\n*** Restarting AODV and entering Mininet-WiFi CLI\n")
            for sta in stations:
                start_aodv(sta, config_map[sta.name], repo_root)
            time.sleep(float(args.aodv_startup_sec))
            CLI(net)

        return 1 if has_failure else 0
    finally:
        for sta in stations:
            stop_aodv(sta)
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    raise SystemExit(main())
