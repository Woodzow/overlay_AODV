"""AODV 运行期数据模型定义。"""

from dataclasses import dataclass, field


@dataclass
class NeighborEntry:
    """邻居表项：记录邻居身份与最近一次 HELLO 时间。"""

    node_id: str
    ip: str
    last_hello_ts: float


@dataclass
class RouteEntry:
    """路由表项（贴近 RFC 语义）。"""

    dest_addr: str
    next_hop: str
    next_hop_ip: str
    hop_count: int
    dest_seq_num: int
    valid: bool
    # 路由状态：VALID / INVALID / REPAIRING
    route_state: str
    expires_at: float


@dataclass
class DataMessage:
    """已送达本节点的业务消息。"""

    src_addr: str
    dest_addr: str
    payload: str
    arrived_ts: float


@dataclass
class PendingPayload:
    """待路由发现完成后再发送的缓存消息。"""

    dest_addr: str
    payload: str


@dataclass
class RouteErrorItem:
    """RERR 不可达目的条目。"""

    dest_addr: str
    dest_seq_num: int


@dataclass
class RuntimeSnapshot:
    """运行状态快照（便于后续扩展调试/监控接口）。"""

    neighbors: list[NeighborEntry] = field(default_factory=list)
    routes: list[RouteEntry] = field(default_factory=list)
    inbox: list[DataMessage] = field(default_factory=list)
