"""节点进程入口。

负责：
- 读取节点配置
- 启动 AODV 协议线程
- 可选启动本地 CLI 线程
"""

import argparse
import time

from aodv_config import NodeConfig
from aodv_protocol import AodvProtocol
from listener import Listener


def run_node(config_path: str, no_cli: bool) -> None:
    """启动节点并维持主循环，直到收到退出信号。"""
    config = NodeConfig.from_file(config_path)
    protocol = AodvProtocol(config)
    protocol.start()

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


def parse_args() -> argparse.Namespace:
    """解析节点启动参数。"""
    parser = argparse.ArgumentParser(description="AODV 应用层覆盖网络节点")
    parser.add_argument("--config", required=True, help="节点配置文件路径")
    parser.add_argument("--no-cli", action="store_true", help="不启动本地交互命令行")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_node(config_path=args.config, no_cli=args.no_cli)
