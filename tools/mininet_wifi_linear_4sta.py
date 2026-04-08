#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a 4-station linear Mininet-WiFi topology for the AODV overlay project."
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Drop into the Mininet-WiFi CLI after the automated test.",
    )
    parser.add_argument(
        "--neighbor-wait-sec",
        type=float,
        default=6.0,
        help="Time to wait for HELLO-based neighbor discovery before sending data.",
    )
    parser.add_argument(
        "--delivery-wait-sec",
        type=float,
        default=8.0,
        help="Time to wait for route discovery and end-to-end data delivery.",
    )
    parser.add_argument(
        "--payload",
        default="hello from sta1 to sta4",
        help="Payload injected from sta1 to sta4.",
    )
    return parser.parse_args()


def run_cmd(node, command: str) -> str:
    return node.cmd(command).strip()


def send_control(node, command: str, timeout_sec: float = 3.0, port: int = 5100) -> str:
    script = (
        "import socket; "
        "sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); "
        f"sock.settimeout({timeout_sec}); "
        f"sock.sendto({command!r}.encode('utf-8'), ('127.0.0.1', {port})); "
        "data,_=sock.recvfrom(8192); "
        "print(data.decode('utf-8', 'ignore'))"
    )
    return run_cmd(node, f"python3 -c {shlex.quote(script)}")


def start_aodv(node, config_path: Path, repo_root: Path) -> None:
    repo_text = shlex.quote(str(repo_root))
    src_text = shlex.quote(str(repo_root / "src"))
    cfg_text = shlex.quote(str(config_path))
    log_text = shlex.quote(f"/tmp/{node.name}-aodv.out")
    cmd = (
        f"cd {repo_text} && "
        f"PYTHONPATH={src_text} "
        f"nohup python3 src/main.py node --config {cfg_text} > {log_text} 2>&1 &"
    )
    node.cmd(cmd)


def stop_aodv(node) -> None:
    node.cmd("pkill -f 'src/main.py node --config' >/dev/null 2>&1 || true")


def print_node_state(node) -> None:
    info(f"\n=== {node.name} neighbors ===\n")
    info(send_control(node, "SHOW_NEIGHBORS") + "\n")
    info(f"=== {node.name} routes ===\n")
    info(send_control(node, "SHOW_ROUTE") + "\n")


def build_topology():
    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference)

    sta1 = net.addStation("sta1", ip="10.0.0.1/24", position="10,50,0", range=45)
    sta2 = net.addStation("sta2", ip="10.0.0.2/24", position="50,50,0", range=45)
    sta3 = net.addStation("sta3", ip="10.0.0.3/24", position="90,50,0", range=45)
    sta4 = net.addStation("sta4", ip="10.0.0.4/24", position="130,50,0", range=45)

    net.setPropagationModel(model="logDistance", exp=4.0)
    net.configureWifiNodes()

    for sta in (sta1, sta2, sta3, sta4):
        net.addLink(
            sta,
            cls=adhoc,
            intf=f"{sta.name}-wlan0",
            ssid="aodv-adhoc",
            mode="g",
            channel=1,
        )

    return net, (sta1, sta2, sta3, sta4)


def main() -> int:
    args = parse_args()

    if os.geteuid() != 0:
        print("This script must be run with sudo/root.", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    config_dir = repo_root / "configs" / "mininet_wifi"
    config_map = {
        "sta1": config_dir / "sta1.json",
        "sta2": config_dir / "sta2.json",
        "sta3": config_dir / "sta3.json",
        "sta4": config_dir / "sta4.json",
    }

    missing = [str(path) for path in config_map.values() if not path.exists()]
    if missing:
        print("Missing config files:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 1

    net, stations = build_topology()
    sta1, sta2, sta3, sta4 = stations

    try:
        info("*** Building Mininet-WiFi network\n")
        net.build()

        info("*** Starting AODV node processes inside station namespaces\n")
        for sta in stations:
            start_aodv(sta, config_map[sta.name], repo_root)

        time.sleep(2.0)

        info(f"*** Waiting {args.neighbor_wait_sec:.1f}s for HELLO discovery\n")
        time.sleep(args.neighbor_wait_sec)

        for sta in stations:
            print_node_state(sta)

        info("*** Sending application payload from sta1 to sta4\n")
        response = send_control(sta1, f"SEND_MESSAGE:10.0.0.4:{args.payload}", timeout_sec=5.0)
        info(response + "\n")

        info(f"*** Waiting {args.delivery_wait_sec:.1f}s for route discovery and delivery\n")
        time.sleep(args.delivery_wait_sec)

        for sta in stations:
            info(f"\n=== {sta.name} routes after send ===\n")
            info(send_control(sta, "SHOW_ROUTE") + "\n")

        info("\n=== sta4 messages ===\n")
        message_box = send_control(sta4, "SHOW_MESSAGES")
        info(message_box + "\n")

        if args.payload in message_box:
            info("*** End-to-end delivery succeeded\n")
        else:
            info("*** Payload not observed at sta4 yet; inspect /tmp/sta*-aodv.out and route tables\n")

        if args.cli:
            info("*** Starting Mininet-WiFi CLI\n")
            CLI(net)
        return 0
    finally:
        info("*** Stopping AODV node processes\n")
        for sta in stations:
            stop_aodv(sta)
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    raise SystemExit(main())
