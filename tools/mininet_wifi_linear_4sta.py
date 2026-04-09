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


VIDEO_DEST_IP = '10.0.0.4'
VIDEO_DATA_PORT = 6200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run a 4-station linear Mininet-WiFi topology and one-click AODV file transfer test.'
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
        default=VIDEO_DEST_IP,
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


def start_video_forwarder(node, node_ip: str, repo_root: Path, output_dir: Path | None = None, data_port: int = VIDEO_DATA_PORT) -> None:
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


def print_underlay_checks(stations) -> None:
    checks = [
        ('sta1', '10.0.0.2'),
        ('sta2', '10.0.0.3'),
        ('sta3', '10.0.0.4'),
    ]
    name_to_node = {node.name: node for node in stations}
    for source_name, target_ip in checks:
        node = name_to_node[source_name]
        info(f'\n=== underlay check: {source_name} -> {target_ip} ===\n')
        info(run_cmd(node, f'ping -c 1 -W 1 {target_ip}') + '\n')


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


def build_topology():
    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference)

    sta1 = net.addStation('sta1', ip='10.0.0.1/24', position='10,50,0', range=45)
    sta2 = net.addStation('sta2', ip='10.0.0.2/24', position='50,50,0', range=45)
    sta3 = net.addStation('sta3', ip='10.0.0.3/24', position='90,50,0', range=45)
    sta4 = net.addStation('sta4', ip='10.0.0.4/24', position='130,50,0', range=45)

    net.setPropagationModel(model='logDistance', exp=4.0)
    net.configureWifiNodes()

    for sta in (sta1, sta2, sta3, sta4):
        net.addLink(
            sta,
            cls=adhoc,
            intf=f'{sta.name}-wlan0',
            ssid='aodv-adhoc',
            mode='g',
            channel=1,
        )

    return net, (sta1, sta2, sta3, sta4)


def sha256sum(node, path: Path) -> str:
    return run_cmd(node, f'sha256sum {shlex.quote(str(path))}').split()[0]


def automated_file_transfer(
    repo_root: Path,
    stations,
    video_file: Path,
    dest_ip: str,
    data_port: int,
    chunk_size: int,
) -> None:
    sta1, sta2, sta3, sta4 = stations
    received_dir = repo_root / 'logs' / 'received_videos'
    received_dir.mkdir(parents=True, exist_ok=True)
    expected_output = received_dir / video_file.name

    for cleanup_path in (expected_output, expected_output.with_suffix(expected_output.suffix + '.part')):
        if cleanup_path.exists():
            cleanup_path.unlink()

    info('*** Starting video_forwarder relay/receiver processes\n')
    start_video_forwarder(sta2, '10.0.0.2', repo_root, data_port=data_port)
    start_video_forwarder(sta3, '10.0.0.3', repo_root, data_port=data_port)
    start_video_forwarder(sta4, '10.0.0.4', repo_root, output_dir=received_dir, data_port=data_port)
    time.sleep(1.0)

    info('*** Sending video file from sta1 to sta4\n')
    send_cmd = (
        f"cd {shlex.quote(str(repo_root))} && "
        f"PYTHONPATH={shlex.quote(str(repo_root / 'src'))} "
        f"python3 src/video_forwarder.py --node-ip 10.0.0.1 "
        f"--data-port {int(data_port)} --send-file {shlex.quote(str(video_file))} "
        f"--dest-ip {dest_ip} --chunk-size {int(chunk_size)} "
        f"--log-file {shlex.quote(str(repo_root / 'logs' / 'mininet_wifi' / 'sta1-video_forwarder.log'))} "
        '--exit-after-send'
    )
    sender_output = run_cmd(sta1, send_cmd)
    info(sender_output + '\n')

    for sta in stations:
        info(f'\n=== {sta.name} routes after file transfer ===\n')
        info(send_control(sta, 'SHOW_ROUTE') + '\n')

    if not expected_output.exists():
        raise RuntimeError(f'received file not found: {expected_output}')

    src_hash = sha256sum(sta1, video_file)
    dst_hash = sha256sum(sta4, expected_output)
    info(f'\n=== file verification ===\nsource={video_file}\ndest={expected_output}\nsha256_src={src_hash}\nsha256_dst={dst_hash}\n')
    if src_hash != dst_hash:
        raise RuntimeError('sha256 mismatch after file transfer')

    info('*** One-click file transfer succeeded\n')


def main() -> int:
    args = parse_args()

    if os.geteuid() != 0:
        print('This script must be run with sudo/root.', file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    video_file = Path(args.video_file)
    if not video_file.is_absolute():
        video_file = repo_root / video_file
    video_file = video_file.resolve()

    if (not args.skip_file_transfer) and (not video_file.is_file()):
        print(f'Video file not found: {video_file}', file=sys.stderr)
        return 1

    config_dir = repo_root / 'configs' / 'mininet_wifi'
    config_map = {
        'sta1': config_dir / 'sta1.json',
        'sta2': config_dir / 'sta2.json',
        'sta3': config_dir / 'sta3.json',
        'sta4': config_dir / 'sta4.json',
    }

    missing = [str(path) for path in config_map.values() if not path.exists()]
    if missing:
        print('Missing config files:', file=sys.stderr)
        for path in missing:
            print(f'  - {path}', file=sys.stderr)
        return 1

    net, stations = build_topology()

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

        print_underlay_checks(stations)

        for sta in stations:
            print_node_state(sta)

        if args.skip_file_transfer:
            info('*** File transfer step skipped by --skip-file-transfer\n')
        else:
            automated_file_transfer(
                repo_root=repo_root,
                stations=stations,
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



