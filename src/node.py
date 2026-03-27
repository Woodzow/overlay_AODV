"""节点进程入口。

负责：
- 读取节点配置
- 启动 AODV 协议线程
- 可选启动本地 CLI 线程
"""

import argparse
import socket
import time

from aodv_config import NodeConfig
from aodv_protocol import AodvProtocol
from listener import Listener


def _default_node_id_from_ip(ip: str) -> str:
    """Use last IPv4 octet as a stable default node id."""
    last_octet = ip.strip().split(".")[-1]
    return f"n{last_octet}"


def build_node_config(args: argparse.Namespace) -> NodeConfig:
    """Build NodeConfig from either JSON file or minimal CLI args."""
    if args.config:
        return NodeConfig.from_file(args.config)

    if not args.ip:
        raise ValueError("node 模式必须提供 --config 或 --ip")

    try:
        socket.inet_aton(args.ip)
    except OSError as exc:
        raise ValueError(f"非法 IPv4 地址: {args.ip}") from exc

    return NodeConfig(
        node_id=(args.node_id or _default_node_id_from_ip(args.ip)),
        bind_ip=args.bind_ip,
        node_ip=args.ip,
        overlay_port=int(args.overlay_port),
        control_bind_ip=args.control_bind_ip,
        control_port=int(args.control_port),
        neighbors=[],
    )


def run_node(config: NodeConfig, no_cli: bool, dest_ip: str | None = None) -> None:
    """启动节点并维持主循环，直到收到退出信号。"""
    protocol = AodvProtocol(config)
    protocol.start()
    if dest_ip:
        deadline = time.time() + 3.0
        while protocol.overlay_sock is None and time.time() < deadline:
            time.sleep(0.05)
        protocol._start_route_discovery(dest_addr=dest_ip, dest_seq_num=0, force=True)
        protocol._trace(f"入口参数触发路由发现: dest={dest_ip}")

    listener = None
    if not no_cli:
        listener = Listener(config.control_bind_ip, config.control_port)
        listener.start()

    try:
        while True:
            # 主线程仅做保活与线程状态检查，核心逻辑在子线程执行。
            time.sleep(1)
            if listener and (not listener.is_alive()):
                break
    except KeyboardInterrupt:
        pass
    finally:
        protocol.stop()
        protocol.join(timeout=3)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析节点启动参数。"""
    parser = argparse.ArgumentParser(description="AODV 应用层覆盖网络节点")
    parser.add_argument("--config", help="节点配置文件路径")
    parser.add_argument("--ip", help="节点 IPv4 地址（无配置文件模式）")
    parser.add_argument("--node-id", help="节点标识（默认按 IP 末段生成，如 n1）")
    parser.add_argument("--bind-ip", default="0.0.0.0", help="overlay 监听地址（默认 0.0.0.0）")
    parser.add_argument("--overlay-port", type=int, default=5005, help="overlay UDP 端口（默认 5005）")
    parser.add_argument("--control-bind-ip", default="0.0.0.0", help="控制面监听地址（默认 0.0.0.0）")
    parser.add_argument("--control-port", type=int, default=5100, help="控制面 UDP 端口（默认 5100）")
    parser.add_argument("--dest-ip", help="启动后立即发起路由发现的目的节点 IP")
    parser.add_argument("--no-cli", action="store_true", help="不启动本地交互命令行")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    node_config = build_node_config(args)
    run_node(config=node_config, no_cli=args.no_cli, dest_ip=args.dest_ip)
