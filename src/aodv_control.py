from __future__ import annotations

"""控制面命令处理器。

协议线程通过 UDP 控制端口接收文本命令，本模块负责解析和执行。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aodv_protocol import AodvProtocol


def _show_route_table(protocol: "AodvProtocol") -> str:
    """Format route table in compact style: Destination | Next Hop | Distance."""
    lines = [
        "Destination     | Next Hop        | Distance",
        "=============================================",
    ]
    with protocol._lock:
        routes = sorted(protocol.routing_table.values(), key=lambda item: item.dest_addr)
        for route in routes:
            if not route.valid:
                continue
            lines.append(f"{route.dest_addr:<15} | {route.next_hop_ip:<15} | {float(route.hop_count):.1f}")
    if len(lines) == 2:
        lines.append("(empty)")
    return "\n".join(lines)


def _show_route_detail(protocol: "AodvProtocol", dest_addr: str) -> str:
    with protocol._lock:
        route = protocol.routing_table.get(dest_addr)
        if route is None:
            return f"未找到路由：{dest_addr}"
        return (
            f"dest={route.dest_addr}\n"
            f"next_hop={route.next_hop}\n"
            f"next_hop_ip={route.next_hop_ip}\n"
            f"hop_count={route.hop_count}\n"
            f"dest_seq_num={route.dest_seq_num}\n"
            f"state={route.route_state}\n"
            f"valid={route.valid}\n"
            f"expires_at={route.expires_at:.3f}"
        )


def _show_neighbors(protocol: "AodvProtocol") -> str:
    """格式化输出当前邻居表。"""
    lines = ["NeighborID  IP", "-------------------------"]
    with protocol._lock:
        for entry in protocol.neighbor_table.values():
            lines.append(f"{entry.node_id:<10} {entry.ip}")
    return "\n".join(lines)


def _show_messages(protocol: "AodvProtocol") -> str:
    """格式化输出消息箱内容。"""
    lines = ["Source  Destination  Payload", "----------------------------"]
    with protocol._lock:
        for item in protocol.message_box:
            lines.append(f"{item.src_addr:<7} {item.dest_addr:<12} {item.payload}")
    return "\n".join(lines)


def _show_discovery(protocol: "AodvProtocol") -> str:
    """格式化输出当前路由发现状态。"""
    lines = ["Destination  Attempts  NextTTL  RetryAt", "-------------------------------------------"]
    with protocol._lock:
        for dest_addr, state in protocol.discovery_manager.snapshot().items():
            lines.append(
                f"{dest_addr:<12} {state.attempts:<8} {state.next_ttl:<7} {state.next_retry_at:.3f}"
            )
    return "\n".join(lines)


def _show_rrep_ack(protocol: "AodvProtocol") -> str:
    """格式化输出等待 RREP-ACK 的邻居列表。"""
    lines = ["NeighborIP       AckDeadline", "----------------------------"]
    with protocol._lock:
        for ip, deadline in protocol.rrep_ack_manager.snapshot().items():
            lines.append(f"{ip:<15} {deadline:.3f}")
    return "\n".join(lines)


def _show_local_repair(protocol: "AodvProtocol") -> str:
    """格式化输出本地修复状态。"""
    lines = ["Destination      SeqNum    Deadline", "------------------------------------"]
    with protocol._lock:
        for dest_addr, state in protocol.local_repair_manager.snapshot().items():
            lines.append(f"{dest_addr:<16} {state.dest_seq_num:<8} {state.deadline_at:.3f}")
    return "\n".join(lines)


def _show_pending_data(protocol: "AodvProtocol") -> str:
    """格式化输出待转发/待发送缓存数据。"""
    lines = ["Destination      BufferedPackets", "-------------------------------"]
    with protocol._lock:
        for dest_addr, items in protocol.pending_data_packets.items():
            lines.append(f"{dest_addr:<16} {len(items)}")
    return "\n".join(lines)


def _show_precursors(protocol: "AodvProtocol") -> str:
    lines = ["Destination      Precursors", "---------------------------------------------"]
    with protocol._lock:
        for dest_addr, peers in protocol.error_manager.precursors.items():
            peer_text = ",".join(sorted(peers)) if peers else "-"
            lines.append(f"{dest_addr:<16} {peer_text}")
    return "\n".join(lines)


def _show_timer(protocol: "AodvProtocol") -> str:
    cfg = protocol.config
    return (
        f"hello_interval_sec={cfg.hello_interval_sec}\n"
        f"hello_timeout_sec={cfg.hello_timeout_sec}\n"
        f"route_lifetime_sec={cfg.route_lifetime_sec}\n"
        f"path_discovery_timeout_sec={cfg.path_discovery_timeout_sec}\n"
        f"rreq_ttl={cfg.rreq_ttl}\n"
        f"rreq_ttl_start={cfg.rreq_ttl_start}\n"
        f"rreq_ttl_increment={cfg.rreq_ttl_increment}\n"
        f"rreq_ttl_threshold={cfg.rreq_ttl_threshold}\n"
        f"rreq_retry_wait_sec={cfg.rreq_retry_wait_sec}\n"
        f"rreq_retries={cfg.rreq_retries}\n"
        f"local_repair_wait_sec={cfg.local_repair_wait_sec}\n"
        f"rrep_ack_timeout_sec={cfg.rrep_ack_timeout_sec}\n"
        f"rerr_rate_limit_sec={cfg.rerr_rate_limit_sec}\n"
        f"tx_jitter_max_ms={cfg.tx_jitter_max_ms}"
    )


def process_control_command(protocol: "AodvProtocol", command_text: str) -> str:
    """处理控制面命令并返回文本响应。

    命令格式为 `OP[:arg1[:arg2]]`，例如：
    - `ADD_NEIGHBOR:n2:192.168.1.11`
    - `SEND_MESSAGE:n3:hello world`
    - `SHOW_ROUTE`

    给 Python 初学者的直观理解：
    - 把 `command_text` 看成“冒号分隔的数组”
      例如 `"ADD_NEIGHBOR:n2:192.168.1.11".split(":", 2)`
      得到 `["ADD_NEIGHBOR", "n2", "192.168.1.11"]`
    """
    parts = command_text.strip().split(":", 2)
    op = parts[0].upper() if parts else ""

    if op == "NODE_ACTIVATE":
        protocol.node_status = "ACTIVE"
        return "节点已激活"

    if op == "NODE_DEACTIVATE":
        protocol.node_status = "INACTIVE"
        return "节点已失活"

    if op == "ADD_NEIGHBOR" and len(parts) >= 3:
        neighbor_id = parts[1].strip()
        neighbor_ip = parts[2].strip()
        protocol.addr_alias[neighbor_id] = neighbor_ip
        protocol.addr_alias[neighbor_ip] = neighbor_ip
        protocol._touch_neighbor(neighbor_ip, neighbor_ip)
        return f"邻居已添加：{neighbor_id} -> {neighbor_ip}"

    if op == "DELETE_NEIGHBOR" and len(parts) >= 2:
        neighbor_id = parts[1].strip()
        neighbor_addr = protocol.resolve_address(neighbor_id)
        if neighbor_addr is None:
            return f"非法地址或未知别名：{neighbor_id}"
        with protocol._lock:
            protocol.neighbor_table.pop(neighbor_addr, None)
            if neighbor_addr in protocol.routing_table:
                protocol.routing_table[neighbor_addr].valid = False
        return f"邻居已删除：{neighbor_id}"

    if op == "SEND_MESSAGE" and len(parts) >= 3:
        dest_addr = parts[1].strip()
        payload = parts[2]
        if not dest_addr:
            return "目标节点不能为空"
        resolved = protocol.resolve_address(dest_addr)
        if resolved is None:
            return f"非法地址或未知别名：{dest_addr}"
        return protocol._send_user_data(dest_addr=resolved, payload=payload)

    if op == "SHOW_ROUTE":
        return _show_route_table(protocol)
    if op == "SHOW_ROUTE_DETAIL" and len(parts) >= 2:
        target = parts[1].strip()
        resolved = protocol.resolve_address(target)
        if not resolved:
            return f"非法地址或未知别名：{target}"
        return _show_route_detail(protocol, resolved)

    if op == "SHOW_NEIGHBORS":
        return _show_neighbors(protocol)

    if op == "SHOW_MESSAGES":
        return _show_messages(protocol)

    if op == "SHOW_DISCOVERY":
        return _show_discovery(protocol)

    if op == "SHOW_RREP_ACK":
        return _show_rrep_ack(protocol)

    if op == "SHOW_LOCAL_REPAIR":
        return _show_local_repair(protocol)

    if op == "SHOW_PENDING_DATA":
        return _show_pending_data(protocol)
    if op == "SHOW_PRECURSORS":
        return _show_precursors(protocol)
    if op == "SHOW_TIMER":
        return _show_timer(protocol)

    if op == "CLEAR_MESSAGES":
        with protocol._lock:
            protocol.message_box.clear()
        return "消息箱已清空"

    if op == "HELP":
        return (
            "支持命令: NODE_ACTIVATE | NODE_DEACTIVATE | ADD_NEIGHBOR:<id>:<ip> | "
            "DELETE_NEIGHBOR:<id> | SEND_MESSAGE:<dest>:<payload> | SHOW_ROUTE | SHOW_ROUTE_DETAIL:<dest> | "
            "SHOW_NEIGHBORS | SHOW_MESSAGES | SHOW_DISCOVERY | SHOW_RREP_ACK | "
            "SHOW_LOCAL_REPAIR | SHOW_PENDING_DATA | SHOW_PRECURSORS | SHOW_TIMER | CLEAR_MESSAGES"
        )

    return "未知命令"
