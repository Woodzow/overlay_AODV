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
    parser.add_argument("--cluster", help="tester 模式下使用的集群配置文件")
    parser.add_argument("--script", help="tester 模式下使用的脚本文件")
    parser.add_argument("--no-cli", action="store_true", help="node 模式不启动本地 CLI")
    return parser.parse_args()


def main() -> int:
    """根据模式转发到对应子程序。"""
    args = parse_args()

    if args.mode == "node":
        if not args.config:
            print("node 模式必须提供 --config")
            return 1
        cmd = [sys.executable, "node.py", "--config", args.config]
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
