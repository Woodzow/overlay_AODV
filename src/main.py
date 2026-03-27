"""统一入口。

为了兼容原项目习惯，保留 `main.py` 作为路由入口：
- `node` 模式：启动单个节点
- `tester` 模式：执行脚本化测试
"""

import argparse
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="AODV 应用层覆盖网络入口")
    parser.add_argument(
        "mode",
        choices=["node", "tester"],
        help="运行模式：node 为节点进程，tester 为脚本测试器",
    )
    parser.add_argument("--config", help="node 模式下使用的节点配置文件")
    parser.add_argument("--ip", help="node 模式下节点 IPv4 地址（无配置文件模式）")
    parser.add_argument("--node-id", help="node 模式下节点标识（可选）")
    parser.add_argument("--bind-ip", help="node 模式下 overlay 监听地址")
    parser.add_argument("--overlay-port", type=int, help="node 模式下 overlay UDP 端口")
    parser.add_argument("--control-bind-ip", help="node 模式下控制面监听地址")
    parser.add_argument("--control-port", type=int, help="node 模式下控制面 UDP 端口")
    parser.add_argument("--cluster", help="tester 模式下使用的集群配置文件")
    parser.add_argument("--script", help="tester 模式下使用的脚本文件")
    parser.add_argument("--no-cli", action="store_true", help="node 模式不启动本地 CLI")
    return parser.parse_args()


def main() -> int:
    """根据模式转发到对应子程序。"""
    args = parse_args()

    if args.mode == "node":
        if (not args.config) and (not args.ip):
            print("node 模式必须提供 --config 或 --ip")
            return 1
        cmd = [sys.executable, "node.py"]
        if args.config:
            cmd.extend(["--config", args.config])
        if args.ip:
            cmd.extend(["--ip", args.ip])
        if args.node_id:
            cmd.extend(["--node-id", args.node_id])
        if args.bind_ip:
            cmd.extend(["--bind-ip", args.bind_ip])
        if args.overlay_port is not None:
            cmd.extend(["--overlay-port", str(args.overlay_port)])
        if args.control_bind_ip:
            cmd.extend(["--control-bind-ip", args.control_bind_ip])
        if args.control_port is not None:
            cmd.extend(["--control-port", str(args.control_port)])
        if args.no_cli:
            cmd.append("--no-cli")
        return subprocess.call(cmd)

    if not args.cluster or not args.script:
        print("tester 模式必须同时提供 --cluster 和 --script")
        return 1

    cmd = [
        sys.executable,
        "tester.py",
        "--cluster",
        args.cluster,
        "--script",
        args.script,
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
