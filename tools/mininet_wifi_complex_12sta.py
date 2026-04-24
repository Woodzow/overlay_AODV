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


TOPOLOGY_FILE = Path(__file__).resolve().parents[1] / 'configs' / 'mininet_wifi_complex_12sta' / 'topology.json'
VIDEO_DATA_PORT = 6200
BENCH_MODE_ROUTE = 'route'
BENCH_MODE_LATENCY = 'latency'
BENCH_MODE_THROUGHPUT = 'throughput'
BENCH_MODES = (BENCH_MODE_ROUTE, BENCH_MODE_LATENCY, BENCH_MODE_THROUGHPUT)


def load_topology() -> dict:
    return json.loads(TOPOLOGY_FILE.read_text(encoding='utf-8'))


def parse_args(topology: dict) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run the 12-station complex Mininet-WiFi topology with one-click AODV file transfer or benchmark automation.'
    )
    parser.add_argument(
        '--cli',
        action='store_true',
        help='Drop into the Mininet-WiFi CLI after the automated test.',
    )
    parser.add_argument(
        '--neighbor-wait-sec',
        type=float,
        default=4.0,
        help='Time to wait before querying neighbor and route state.',
    )
    parser.add_argument(
        '--video-file',
        default='data.mp4',
        help='Video file path relative to repo root, or absolute path if needed.',
    )
    parser.add_argument(
        '--video-dest-ip',
        default=topology['video_dest_ip'],
        help='Destination node IP for the automated file transfer.',
    )
    parser.add_argument(
        '--video-data-port',
        type=int,
        default=VIDEO_DATA_PORT,
        help='UDP data port used by video_forwarder.py.',
    )
    parser.add_argument(
        '--video-chunk-size',
        type=int,
        default=900,
        help='Raw bytes per file chunk before base64 in video_forwarder.py.',
    )
    parser.add_argument(
        '--skip-file-transfer',
        action='store_true',
        help='Only build topology and AODV processes, do not run the file transfer demo.',
    )
    parser.add_argument(
        '--link-loss',
        type=float,
        default=0.0,
        help='Apply tc netem packet loss percentage on each sta wlan interface, e.g. 5 for 5%%.',
    )
    parser.add_argument(
        '--bench',
        choices=BENCH_MODES,
        help='Run one overlay benchmark round after AODV startup. route does not need remote daemons; latency/throughput auto-start them.',
    )
    parser.add_argument(
        '--bench-source',
        default=topology.get('video_source', 'sta1'),
        help='Source station used by --bench. Default follows the topology file.',
    )
    parser.add_argument(
        '--bench-dest',
        default=topology.get('video_dest', 'sta12'),
        help='Destination station used by --bench. Default follows the topology file.',
    )
    parser.add_argument(
        '--bench-daemon-startup-sec',
        type=float,
        default=1.0,
        help='Time to wait after auto-starting overlay_bench daemons for latency/throughput.',
    )
    parser.add_argument(
        '--bench-route-timeout-sec',
        type=float,
        default=12.0,
        help='Max time to wait for route establishment in overlay_bench benchmark mode.',
    )
    parser.add_argument(
        '--bench-route-poll-interval-sec',
        type=float,
        default=0.2,
        help='Polling interval while waiting for routes in overlay_bench benchmark mode.',
    )
    parser.add_argument(
        '--bench-count',
        type=int,
        help='Packet/probe count for benchmark mode. Defaults: latency=20, throughput=1000.',
    )
    parser.add_argument(
        '--bench-payload-size',
        type=int,
        help='Payload size in bytes for benchmark mode. Defaults: latency=64, throughput=1000.',
    )
    parser.add_argument(
        '--bench-interval-ms',
        type=float,
        help='Send interval in milliseconds for benchmark mode. Defaults: latency=100, throughput=0.',
    )
    parser.add_argument(
        '--bench-reply-timeout-sec',
        type=float,
        default=3.0,
        help='Per-probe reply timeout used by latency benchmark mode.',
    )
    parser.add_argument(
        '--bench-report-timeout-sec',
        type=float,
        default=10.0,
        help='Timeout waiting for the destination report in throughput benchmark mode.',
    )
    return parser.parse_args()


def run_cmd(node, command: str) -> str:
    return node.cmd(command).strip()


def send_control(node, command: str, timeout_sec: float = 3.0, port: int = 5100) -> str:
    script = (
        'import socket; '
        'sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); '
        f'sock.settimeout({timeout_sec}); '
        f"sock.sendto({command!r}.encode('utf-8'), ('127.0.0.1', {port})); "
        "data,_=sock.recvfrom(8192); "
        "print(data.decode('utf-8', 'ignore'))"
    )
    return run_cmd(node, f"python3 -c {shlex.quote(script)}")


def start_aodv(node, config_path: Path, repo_root: Path) -> None:
    repo_text = shlex.quote(str(repo_root))
    src_text = shlex.quote(str(repo_root / 'src'))
    cfg_text = shlex.quote(str(config_path))
    log_dir = repo_root / 'logs' / 'mininet_wifi'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_text = shlex.quote(str(log_dir / f'{node.name}-aodv.out'))
    cmd = (
        f"cd {repo_text} && "
        f"PYTHONPATH={src_text} "
        f"nohup python3 src/main.py node --config {cfg_text} > {log_text} 2>&1 &"
    )
    node.cmd(cmd)


def stop_aodv(node) -> None:
    node.cmd("pkill -f 'src/main.py node --config' >/dev/null 2>&1 || true")


def start_video_forwarder(
    node,
    node_ip: str,
    repo_root: Path,
    output_dir: Path | None = None,
    data_port: int = VIDEO_DATA_PORT,
) -> None:
    repo_text = shlex.quote(str(repo_root))
    src_text = shlex.quote(str(repo_root / 'src'))
    log_dir = repo_root / 'logs' / 'mininet_wifi'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_text = shlex.quote(str(log_dir / f'{node.name}-video_forwarder.log'))
    cmd_parts = [
        f"cd {repo_text}",
        f"PYTHONPATH={src_text} nohup python3 src/video_forwarder.py --node-ip {node_ip} --data-port {int(data_port)}",
    ]
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd_parts[-1] += f" --output-dir {shlex.quote(str(output_dir))}"
    cmd_parts[-1] += f" --log-file {log_text} > /dev/null 2>&1 &"
    node.cmd(' && '.join(cmd_parts))


def stop_video_forwarder(node) -> None:
    node.cmd("pkill -f 'src/video_forwarder.py --node-ip' >/dev/null 2>&1 || true")


def start_bench_daemon(node, node_ip: str, repo_root: Path) -> None:
    repo_text = shlex.quote(str(repo_root))
    src_text = shlex.quote(str(repo_root / 'src'))
    log_dir = repo_root / 'logs' / 'mininet_wifi'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_text = shlex.quote(str(log_dir / f'{node.name}-bench.log'))
    cmd = (
        f"cd {repo_text} && "
        f"PYTHONPATH={src_text} "
        f"nohup python3 src/overlay_bench.py daemon --node-ip {node_ip} --quiet --log-file {log_text} "
        '> /dev/null 2>&1 &'
    )
    node.cmd(cmd)


def stop_bench_daemon(node) -> None:
    node.cmd("pkill -f 'overlay_bench.py daemon' >/dev/null 2>&1 || true")


def source_ip_of(topology: dict, station_name: str) -> str:
    for item in topology['stations']:
        if item['name'] == station_name:
            return str(item['ip']).split('/', 1)[0]
    raise KeyError(f'unknown station in topology: {station_name}')


def station_name_of_ip(topology: dict, target_ip: str) -> str:
    for item in topology['stations']:
        station_ip = str(item['ip']).split('/', 1)[0]
        if station_ip == target_ip:
            return item['name']
    raise KeyError(f'unknown destination ip in topology: {target_ip}')


def validate_bench_args(args: argparse.Namespace, topology: dict) -> None:
    if not args.bench:
        return
    station_names = {item['name'] for item in topology['stations']}
    if args.bench_source not in station_names:
        raise ValueError(f'unknown --bench-source: {args.bench_source}')
    if args.bench_dest not in station_names:
        raise ValueError(f'unknown --bench-dest: {args.bench_dest}')
    if args.bench_source == args.bench_dest:
        raise ValueError('--bench-source and --bench-dest must be different stations')
    if args.bench_count is not None and args.bench_count <= 0:
        raise ValueError('--bench-count must be greater than zero')
    if args.bench_payload_size is not None and args.bench_payload_size <= 0:
        raise ValueError('--bench-payload-size must be greater than zero')
    if args.bench_interval_ms is not None and args.bench_interval_ms < 0:
        raise ValueError('--bench-interval-ms must be non-negative')


def topology_edges(topology: dict) -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for node_name, neighbors in topology['edges'].items():
        for neighbor_name in neighbors:
            pairs.add(tuple(sorted((node_name, neighbor_name))))
    return sorted(pairs)


def print_underlay_checks(stations_by_name: dict[str, object], topology: dict) -> None:
    for source_name, target_name in topology_edges(topology):
        source = stations_by_name[source_name]
        target_ip = source_ip_of(topology, target_name)
        info(f'\n=== underlay check: {source_name} -> {target_ip} ===\n')
        info(run_cmd(source, f'ping -c 1 -W 1 {target_ip}') + '\n')


def print_node_state(node) -> None:
    info(f'\n=== {node.name} neighbors ===\n')
    info(send_control(node, 'SHOW_NEIGHBORS') + '\n')
    info(f'=== {node.name} routes ===\n')
    info(send_control(node, 'SHOW_ROUTE') + '\n')


def apply_link_loss(stations, loss_percent: float) -> None:
    if loss_percent <= 0:
        return

    info(f'*** Applying tc netem loss={loss_percent:.2f}% on sta wlan interfaces\n')
    for sta in stations:
        intf = f'{sta.name}-wlan0'
        sta.cmd(f'tc qdisc replace dev {intf} root netem loss {loss_percent:.2f}%')
        qdisc_state = run_cmd(sta, f'tc qdisc show dev {intf}')
        info(f'[{sta.name}] {qdisc_state}\n')


def extract_json_result(text: str) -> dict:
    for line in reversed([item.strip() for item in text.splitlines() if item.strip()]):
        if line.startswith('{') and line.endswith('}'):
            return json.loads(line)
    raise ValueError(f'benchmark output did not contain a JSON object: {text}')


def build_topology(topology: dict):
    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference)
    radio_range = float(topology['radio_range'])

    stations = []
    for item in topology['stations']:
        station = net.addStation(
            item['name'],
            ip=item['ip'],
            position=f"{item['x']},{item['y']},0",
            range=radio_range,
        )
        stations.append(station)

    net.setPropagationModel(
        model=topology.get('propagation_model', 'logDistance'),
        exp=float(topology.get('propagation_exp', 4.0)),
    )
    net.configureWifiNodes()

    for sta in stations:
        net.addLink(
            sta,
            cls=adhoc,
            intf=f'{sta.name}-wlan0',
            ssid=topology.get('ssid', 'aodv-adhoc'),
            mode=topology.get('mode', 'g'),
            channel=int(topology.get('channel', 1)),
        )

    return net, tuple(stations)


def sha256sum(node, path: Path) -> str:
    return run_cmd(node, f'sha256sum {shlex.quote(str(path))}').split()[0]


def automated_file_transfer(
    repo_root: Path,
    stations,
    topology: dict,
    video_file: Path,
    dest_ip: str,
    data_port: int,
    chunk_size: int,
) -> None:
    source_name = topology['video_source']
    dest_name = station_name_of_ip(topology, dest_ip)
    stations_by_name = {node.name: node for node in stations}
    source_node = stations_by_name[source_name]
    received_dir = repo_root / 'logs' / 'received_videos'
    received_dir.mkdir(parents=True, exist_ok=True)
    expected_output = received_dir / video_file.name

    for cleanup_path in (expected_output, expected_output.with_suffix(expected_output.suffix + '.part')):
        if cleanup_path.exists():
            cleanup_path.unlink()

    info('*** Starting video_forwarder relay/receiver processes\n')
    for node in stations:
        if node.name == source_name:
            continue
        node_ip = source_ip_of(topology, node.name)
        if node.name == dest_name:
            start_video_forwarder(node, node_ip, repo_root, output_dir=received_dir, data_port=data_port)
        else:
            start_video_forwarder(node, node_ip, repo_root, data_port=data_port)
    time.sleep(1.0)

    info(f'*** Sending video file from {source_name} to {dest_name}\n')
    send_cmd = (
        f"cd {shlex.quote(str(repo_root))} && "
        f"PYTHONPATH={shlex.quote(str(repo_root / 'src'))} "
        f"python3 src/video_forwarder.py --node-ip {source_ip_of(topology, source_name)} "
        f"--data-port {int(data_port)} --send-file {shlex.quote(str(video_file))} "
        f"--dest-ip {dest_ip} --chunk-size {int(chunk_size)} "
        f"--log-file {shlex.quote(str(repo_root / 'logs' / 'mininet_wifi' / f'{source_name}-video_forwarder.log'))} "
        '--exit-after-send'
    )
    sender_output = run_cmd(source_node, send_cmd)
    info(sender_output + '\n')

    for sta in stations:
        info(f'\n=== {sta.name} routes after file transfer ===\n')
        info(send_control(sta, 'SHOW_ROUTE') + '\n')

    if not expected_output.exists():
        raise RuntimeError(f'received file not found: {expected_output}')

    src_hash = sha256sum(source_node, video_file)
    dst_hash = sha256sum(stations_by_name[dest_name], expected_output)
    info(
        f'\n=== file verification ===\nsource={video_file}\ndest={expected_output}\n'
        f'sha256_src={src_hash}\nsha256_dst={dst_hash}\n'
    )
    if src_hash != dst_hash:
        raise RuntimeError('sha256 mismatch after file transfer')

    info('*** One-click file transfer succeeded\n')


def benchmark_requires_remote_daemons(bench_mode: str) -> bool:
    return bench_mode in {BENCH_MODE_LATENCY, BENCH_MODE_THROUGHPUT}


def bench_count(args: argparse.Namespace) -> int:
    if args.bench_count is not None:
        return int(args.bench_count)
    if args.bench == BENCH_MODE_LATENCY:
        return 20
    if args.bench == BENCH_MODE_THROUGHPUT:
        return 1000
    raise ValueError(f'unsupported benchmark mode for count: {args.bench}')


def bench_payload_size(args: argparse.Namespace) -> int:
    if args.bench_payload_size is not None:
        return int(args.bench_payload_size)
    if args.bench == BENCH_MODE_LATENCY:
        return 64
    if args.bench == BENCH_MODE_THROUGHPUT:
        return 1000
    raise ValueError(f'unsupported benchmark mode for payload size: {args.bench}')


def bench_interval_ms(args: argparse.Namespace) -> float:
    if args.bench_interval_ms is not None:
        return float(args.bench_interval_ms)
    if args.bench == BENCH_MODE_LATENCY:
        return 100.0
    if args.bench == BENCH_MODE_THROUGHPUT:
        return 0.0
    raise ValueError(f'unsupported benchmark mode for interval: {args.bench}')


def run_overlay_bench(
    source_node,
    source_ip: str,
    dest_ip: str,
    repo_root: Path,
    args: argparse.Namespace,
) -> dict:
    command = (
        f"cd {shlex.quote(str(repo_root))} && "
        f"PYTHONPATH={shlex.quote(str(repo_root / 'src'))} "
        f"python3 src/overlay_bench.py {args.bench} "
        f"--node-ip {source_ip} "
        f"--dest-ip {dest_ip} "
        f"--route-timeout-sec {float(args.bench_route_timeout_sec)} "
        f"--route-poll-interval-sec {float(args.bench_route_poll_interval_sec)} "
        '--quiet --json'
    )
    if args.bench == BENCH_MODE_LATENCY:
        command += (
            f" --count {bench_count(args)}"
            f" --payload-size {bench_payload_size(args)}"
            f" --interval-ms {bench_interval_ms(args)}"
            f" --reply-timeout-sec {float(args.bench_reply_timeout_sec)}"
        )
    elif args.bench == BENCH_MODE_THROUGHPUT:
        command += (
            f" --count {bench_count(args)}"
            f" --payload-size {bench_payload_size(args)}"
            f" --interval-ms {bench_interval_ms(args)}"
            f" --report-timeout-sec {float(args.bench_report_timeout_sec)}"
        )
    output = run_cmd(source_node, command)
    return extract_json_result(output)


def print_bench_result(result: dict) -> None:
    info('\n=== overlay benchmark result ===\n')
    for key, value in result.items():
        info(f'{key}={value}\n')
    info('json=' + json.dumps(result, ensure_ascii=True, separators=(',', ':')) + '\n')


def run_one_click_benchmark(repo_root: Path, stations, topology: dict, args: argparse.Namespace) -> None:
    stations_by_name = {node.name: node for node in stations}
    source_name = args.bench_source
    dest_name = args.bench_dest
    source_node = stations_by_name[source_name]
    source_ip = source_ip_of(topology, source_name)
    dest_ip = source_ip_of(topology, dest_name)

    if benchmark_requires_remote_daemons(args.bench):
        info('*** Auto-starting overlay_bench daemons on relay/destination nodes\n')
        for node in stations:
            if node.name == source_name:
                continue
            start_bench_daemon(node, source_ip_of(topology, node.name), repo_root)
        time.sleep(float(args.bench_daemon_startup_sec))

    info(f'*** Running one-click benchmark mode={args.bench} ({source_name} -> {dest_name})\n')
    result = run_overlay_bench(
        source_node=source_node,
        source_ip=source_ip,
        dest_ip=dest_ip,
        repo_root=repo_root,
        args=args,
    )
    result['source'] = source_name
    result['destination'] = dest_name
    print_bench_result(result)


def main() -> int:
    topology = load_topology()
    args = parse_args(topology)

    try:
        validate_bench_args(args, topology)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if os.geteuid() != 0:
        print('This script must be run with sudo/root.', file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    video_file = Path(args.video_file)
    if not video_file.is_absolute():
        video_file = repo_root / video_file
    video_file = video_file.resolve()

    if (not args.bench) and (not args.skip_file_transfer) and (not video_file.is_file()):
        print(f'Video file not found: {video_file}', file=sys.stderr)
        return 1

    config_dir = repo_root / 'configs' / 'mininet_wifi_complex_12sta'
    config_map = {
        item['name']: config_dir / f"{item['name']}.json"
        for item in topology['stations']
    }

    missing = [str(path) for path in config_map.values() if not path.exists()]
    if missing:
        print('Missing config files:', file=sys.stderr)
        for path in missing:
            print(f'  - {path}', file=sys.stderr)
        return 1

    net, stations = build_topology(topology)

    try:
        info('*** Building Mininet-WiFi network\n')
        net.build()

        apply_link_loss(stations, args.link_loss)

        info('*** Starting AODV node processes inside station namespaces\n')
        for sta in stations:
            start_aodv(sta, config_map[sta.name], repo_root)

        time.sleep(2.0)

        info(f'*** Waiting {args.neighbor_wait_sec:.1f}s before querying AODV state\n')
        time.sleep(args.neighbor_wait_sec)

        if args.bench:
            info('*** Benchmark mode enabled; skipping full underlay/AODV state dump\n')
            if not args.skip_file_transfer:
                info('*** Benchmark mode requested; skipping file transfer step\n')
            run_one_click_benchmark(
                repo_root=repo_root,
                stations=stations,
                topology=topology,
                args=args,
            )
        elif args.skip_file_transfer:
            info('*** File transfer step skipped by --skip-file-transfer\n')
        else:
            stations_by_name = {node.name: node for node in stations}
            print_underlay_checks(stations_by_name, topology)

            for sta in stations:
                print_node_state(sta)
            automated_file_transfer(
                repo_root=repo_root,
                stations=stations,
                topology=topology,
                video_file=video_file,
                dest_ip=args.video_dest_ip,
                data_port=args.video_data_port,
                chunk_size=args.video_chunk_size,
            )

        if args.cli:
            info('*** Starting Mininet-WiFi CLI\n')
            CLI(net)
        return 0
    finally:
        info('*** Stopping overlay_bench daemons\n')
        for sta in stations:
            stop_bench_daemon(sta)
        info('*** Stopping video_forwarder processes\n')
        for sta in stations:
            stop_video_forwarder(sta)
        info('*** Stopping AODV node processes\n')
        for sta in stations:
            stop_aodv(sta)
        net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    raise SystemExit(main())
