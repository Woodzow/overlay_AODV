"""节点配置模型与加载逻辑。

该模块负责把 JSON 配置转换为强类型对象，供协议层直接使用。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class NeighborConfig:
    """静态邻居配置。"""

    node_id: str
    ip: str


@dataclass
class NodeConfig:
    """单个节点运行参数。

    包含两类参数：
    1) 数据面参数：overlay 端口、HELLO/路由超时等
    2) 控制面参数：本地控制端口（CLI / tester 下发命令）

    JSON 配置示例：
    {
      "node_id": "n1",
      "bind_ip": "0.0.0.0",
      "overlay_port": 5005,
      "control_bind_ip": "0.0.0.0",
      "control_port": 5101,
      "neighbors": [{"node_id": "n2", "ip": "192.168.1.11"}]
    }
    """

    node_id: str
    bind_ip: str = "0.0.0.0"
    node_ip: str = "127.0.0.1"
    overlay_port: int = 5005
    control_bind_ip: str = "127.0.0.1"
    control_port: int = 5100
    hello_interval_sec: int = 10
    hello_timeout_sec: int = 30
    route_lifetime_sec: int = 300
    path_discovery_timeout_sec: int = 30
    rreq_ttl: int = 16
    rreq_ttl_start: int = 2
    rreq_ttl_increment: int = 2
    rreq_ttl_threshold: int = 7
    rreq_retry_wait_sec: int = 2
    rreq_retries: int = 3
    local_repair_enabled: bool = True
    local_repair_wait_sec: int = 5
    rrep_ack_enabled: bool = True
    rrep_ack_timeout_sec: int = 2
    rerr_rate_limit_sec: int = 1
    rerr_max_dest_per_msg: int = 16
    tx_jitter_max_ms: int = 30
    pending_queue_limit_per_dest: int = 32
    pending_total_limit: int = 256
    neighbors: list[NeighborConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodeConfig":
        """从 Python 字典构建配置对象。"""
        neighbors = [
            NeighborConfig(node_id=item["node_id"], ip=item["ip"])
            for item in data.get("neighbors", [])
        ]

        return cls(
            node_id=data["node_id"],
            bind_ip=data.get("bind_ip", "0.0.0.0"),
            node_ip=data.get("node_ip", "127.0.0.1"),
            overlay_port=int(data.get("overlay_port", 5005)),
            control_bind_ip=data.get("control_bind_ip", "127.0.0.1"),
            control_port=int(data.get("control_port", 5100)),
            hello_interval_sec=int(data.get("hello_interval_sec", 10)),
            hello_timeout_sec=int(data.get("hello_timeout_sec", 30)),
            route_lifetime_sec=int(data.get("route_lifetime_sec", 300)),
            path_discovery_timeout_sec=int(data.get("path_discovery_timeout_sec", 30)),
            rreq_ttl=int(data.get("rreq_ttl", 16)),
            rreq_ttl_start=int(data.get("rreq_ttl_start", 2)),
            rreq_ttl_increment=int(data.get("rreq_ttl_increment", 2)),
            rreq_ttl_threshold=int(data.get("rreq_ttl_threshold", 7)),
            rreq_retry_wait_sec=int(data.get("rreq_retry_wait_sec", 2)),
            rreq_retries=int(data.get("rreq_retries", 3)),
            local_repair_enabled=bool(data.get("local_repair_enabled", True)),
            local_repair_wait_sec=int(data.get("local_repair_wait_sec", 5)),
            rrep_ack_enabled=bool(data.get("rrep_ack_enabled", True)),
            rrep_ack_timeout_sec=int(data.get("rrep_ack_timeout_sec", 2)),
            rerr_rate_limit_sec=int(data.get("rerr_rate_limit_sec", 1)),
            rerr_max_dest_per_msg=int(data.get("rerr_max_dest_per_msg", 16)),
            tx_jitter_max_ms=int(data.get("tx_jitter_max_ms", 30)),
            pending_queue_limit_per_dest=int(data.get("pending_queue_limit_per_dest", 32)),
            pending_total_limit=int(data.get("pending_total_limit", 256)),
            neighbors=neighbors,
        )

    @classmethod
    def from_file(cls, path: str) -> "NodeConfig":
        """从 JSON 文件读取并构建配置对象。"""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
