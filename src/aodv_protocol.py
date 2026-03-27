"""AODV 协议核心线程（管理器化版本）。"""
import logging
import os
import random
import select
import socket
import threading
import time

from aodv_ack_manager import RrepAckManager
from aodv_codec import (
    RREP_FLAG_ACK_REQUIRED,
    RREQ_FLAG_DEST_ONLY,
    RREQ_FLAG_GRATUITOUS,
    RREQ_FLAG_JOIN,
    RREQ_FLAG_REPAIR,
    RREQ_FLAG_UNKNOWN_SEQ,
    decode_packet,
    encode_packet,
)
from aodv_config import NodeConfig
from aodv_control import process_control_command
from aodv_discovery_manager import DiscoveryManager
from aodv_duplicate_set import DuplicateSet
from aodv_error_manager import ErrorManager
from aodv_local_repair_manager import LocalRepairManager
from aodv_models import DataMessage, NeighborEntry, RouteEntry
from aodv_neighbor_manager import NeighborManager
from aodv_route_manager import RouteManager
from aodv_sequence import is_seq_newer

class AodvProtocol(threading.Thread):
    """负责邻居发现、路由发现、转发与路由维护。"""

    def __init__(self, config: NodeConfig):
        super().__init__(daemon=True)
        self.config = config
        self.node_id = config.node_id
        self.node_addr = config.node_ip
        self.seq_num = 1
        self.rreq_id = 0
        self.node_status = "ACTIVE"
        self.neighbor_table: dict[str, NeighborEntry] = {}
        self.routing_table: dict[str, RouteEntry] = {}
        # 已送达本节点的数据消息（供控制面 show_messages 命令读取）
        self.message_box: list[DataMessage] = []
        # 按目的地址缓存“待发送的完整 DATA 报文字典”，避免丢失 orig_addr/hop_count/ttl 语义
        self.pending_data_packets: dict[str, list[dict]] = {}
        self.last_hello_ts = 0.0
        self.overlay_sock: socket.socket | None = None
        self.control_sock: socket.socket | None = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self.log_file = os.path.join("Logs", f"aodv_log_{self.node_id}")
        os.makedirs("Logs", exist_ok=True)
        self.addr_alias: dict[str, str] = {
            self.node_id: self.node_addr,
            self.node_addr: self.node_addr,
        }
        self.duplicate_set = DuplicateSet()
        self.discovery_manager = DiscoveryManager()
        self.local_repair_manager = LocalRepairManager()
        self.rrep_ack_manager = RrepAckManager()
        self.error_manager = ErrorManager()
        self.neighbor_manager = NeighborManager(self.neighbor_table, self.addr_alias)
        self.route_manager = RouteManager(self.routing_table)

    def _log_event(self, event: str, **fields: object) -> None:
        detail = " ".join(f"{k}={v}" for k, v in fields.items())
        self.logger.debug(f"event={event} {detail}".strip())

    def stop(self) -> None:
        self._stop_event.set()

    def _init_logger(self) -> None:
        logger = logging.getLogger(f"aodv-{self.node_id}")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()

        formatter = logging.Formatter("%(asctime)s - %(message)s")
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        self.logger = logger

    def _bootstrap_neighbors(self) -> None:
        now = time.time()
        with self._lock:
            for item in self.config.neighbors:
                self.addr_alias[item.node_id] = item.ip
                self.addr_alias[item.ip] = item.ip
                self.neighbor_manager.touch(item.ip, item.ip, now)
                self.route_manager.upsert_connected(item.ip, item.ip, now, self.config.route_lifetime_sec)

    def resolve_address(self, target: str) -> str | None:
        value = target.strip()
        if not value:
            return None

        mapped = self.addr_alias.get(value, value)
        try:
            socket.inet_aton(mapped)
            return mapped
        except OSError:
            return None

    def _send_packet_to_ip(self, target_ip: str, packet: dict) -> None:
        if self.overlay_sock is None:
            return
        try:
            payload = encode_packet(packet)
            self.overlay_sock.sendto(payload, (target_ip, self.config.overlay_port))
        except Exception:
            self.logger.exception("发送覆盖网络报文失败")

    def _jitter_sleep(self) -> None:
        max_ms = int(getattr(self.config, "tx_jitter_max_ms", 0))
        if max_ms <= 0:
            return
        time.sleep(random.uniform(0.0, max_ms / 1000.0))

    def _broadcast_to_neighbors(self, packet: dict, exclude_node: str | None = None) -> None:
        with self._lock:
            neighbors = list(self.neighbor_table.values())

        for item in neighbors:
            if exclude_node and item.ip == exclude_node:
                continue
            self._jitter_sleep()
            self._send_packet_to_ip(item.ip, packet)

    def _send_rerr(self, unreachable: list[dict], exclude_node: str | None = None) -> None:
        compact = self.error_manager.normalize_unreachable(
            unreachable, max_items=self.config.rerr_max_dest_per_msg
        )
        if not compact:
            return

        packet = {
            "type": "RERR",
            "sender": self.node_addr,
            "flags": 0,
            "unreachable": compact,
        }
        if not self.error_manager.should_emit_rerr(packet["unreachable"], time.time(), self.config.rerr_rate_limit_sec):
            return

        targets = self.error_manager.targets_for_unreachable(packet["unreachable"])
        if exclude_node:
            targets.discard(exclude_node)
        for ip in targets:
            self._send_packet_to_ip(ip, packet)
        self._log_event("send_rerr", items=len(packet["unreachable"]), targets=len(targets))

    def _send_hello(self) -> None:
        if self.node_status != "ACTIVE":
            return

        packet = {
            "type": "RREP",
            "sender": self.node_addr,
            "flags": 0,
            "prefix_size": 0,
            "hop_count": 0,
            "ttl": 1,
            "dest_addr": self.node_addr,
            "dest_seq_num": self.seq_num,
            "orig_addr": self.node_addr,
            "lifetime": max(1, self.config.hello_timeout_sec),
        }
        self._broadcast_to_neighbors(packet)
        if self.config.auto_neighbor_discovery:
            with self._lock:
                has_neighbors = bool(self.neighbor_table)
            if not has_neighbors:
                # No static/dynamic neighbors yet: send HELLO to broadcast to discover peers.
                self._send_packet_to_ip(self.config.discovery_broadcast_ip, packet)
        self.last_hello_ts = time.time()
        self._log_event("send_hello", ttl=1)

    def _queue_data_packet(self, dest_addr: str, packet: dict) -> None:
        self.pending_data_packets.setdefault(dest_addr, []).append(dict(packet))
        self._enforce_pending_limits(dest_addr)

    def _pending_total_count(self) -> int:
        return sum(len(items) for items in self.pending_data_packets.values())

    def _enforce_pending_limits(self, focus_dest: str) -> None:
        per_dest_limit = max(1, int(self.config.pending_queue_limit_per_dest))
        total_limit = max(1, int(self.config.pending_total_limit))
        queue = self.pending_data_packets.get(focus_dest, [])
        while len(queue) > per_dest_limit:
            queue.pop(0)

        while self._pending_total_count() > total_limit:
            oldest_dest = None
            oldest_len = 0
            for dest, items in self.pending_data_packets.items():
                if len(items) > oldest_len:
                    oldest_dest = dest
                    oldest_len = len(items)
            if not oldest_dest:
                break
            self.pending_data_packets[oldest_dest].pop(0)

    def _drop_pending_data(self, dest_addr: str) -> None:
        self.pending_data_packets.pop(dest_addr, None)

    def _maybe_start_local_repair(self, unreachable: list[dict], allow_repair: bool = True) -> list[dict]:
        """对不可达条目尝试本地修复，返回仍需立即发送 RERR 的条目。"""
        if (not self.config.local_repair_enabled) or (not allow_repair):
            return unreachable

        now = time.time()
        remaining: list[dict] = []
        for item in unreachable:
            dest_addr = item.get("dest_addr")
            if not dest_addr:
                continue
            dest_seq_num = int(item.get("dest_seq_num", 0))
            if self.local_repair_manager.is_repairing(dest_addr):
                continue
            self.local_repair_manager.start(dest_addr, dest_seq_num, now, self.config.local_repair_wait_sec)
            self.route_manager.mark_local_repairing(dest_addr, now, self.config.local_repair_wait_sec)
            self._start_route_discovery(dest_addr, dest_seq_num, force=True, is_local_repair=True)
            self._log_event("local_repair_start", dest=dest_addr, seq=dest_seq_num)
        return remaining

    def _flush_pending_data(self, dest_addr: str) -> None:
        route = self.route_manager.get_valid(dest_addr, time.time())
        if route is None:
            return
        buffered = list(self.pending_data_packets.get(dest_addr, []))
        self.pending_data_packets[dest_addr] = []
        for packet in buffered:
            self._send_packet_to_ip(route.next_hop_ip, packet)

    def _build_forward_data_packet(self, packet: dict) -> dict | None:
        ttl = int(packet.get("ttl", 0))
        hop_count = int(packet.get("hop_count", 0))
        next_ttl = (ttl - 1) & 0xFF
        if next_ttl == 0:
            return None
        fwd = dict(packet)
        fwd["sender"] = self.node_addr
        fwd["hop_count"] = (hop_count + 1) & 0xFF
        fwd["ttl"] = next_ttl
        return fwd

    def _start_route_discovery(
        self,
        dest_addr: str,
        dest_seq_num: int = 0,
        force: bool = False,
        is_local_repair: bool = False,
    ) -> None:
        if self.node_status != "ACTIVE":
            return

        now = time.time()
        if (not force) and (
            not self.discovery_manager.should_send(dest_addr, now, self.config.rreq_retries)
        ):
            return

        self.seq_num = (self.seq_num + 1) & 0xFFFFFFFF
        self.rreq_id = (self.rreq_id + 1) & 0xFFFFFFFF

        key = (self.node_addr, self.rreq_id)
        expires_at = now + self.config.path_discovery_timeout_sec
        self.duplicate_set.remember(key, expires_at)
        ttl = self.discovery_manager.current_ttl(
            dest_addr=dest_addr,
            ttl_start=self.config.rreq_ttl_start,
            ttl_increment=self.config.rreq_ttl_increment,
            ttl_threshold=self.config.rreq_ttl_threshold,
            max_ttl=self.config.rreq_ttl,
        )

        flags = 0
        if int(dest_seq_num) <= 0:
            flags |= RREQ_FLAG_UNKNOWN_SEQ
        if is_local_repair:
            flags |= RREQ_FLAG_REPAIR

        packet = {
            "type": "RREQ",
            "sender": self.node_addr,
            "flags": flags,
            "hop_count": 0,
            "ttl": ttl,
            "rreq_id": self.rreq_id,
            "dest_addr": dest_addr,
            "dest_seq_num": int(dest_seq_num) & 0xFFFFFFFF,
            "orig_addr": self.node_addr,
            "orig_seq_num": self.seq_num,
        }
        self._broadcast_to_neighbors(packet)
        self.discovery_manager.mark_sent(dest_addr, ttl, now, self.config.rreq_retry_wait_sec)
        self._log_event("send_rreq", dest=dest_addr, rreq_id=self.rreq_id, ttl=ttl)

    def _send_rrep(
        self,
        orig_addr: str,
        next_hop_ip: str,
        dest_addr: str,
        dest_seq_num: int,
        hop_count: int,
        ttl: int | None = None,
        require_ack: bool | None = None,
    ) -> None:
        effective_ttl = self.config.rreq_ttl if ttl is None else max(1, int(ttl))
        ack_required = self.config.rrep_ack_enabled if require_ack is None else require_ack
        flags = RREP_FLAG_ACK_REQUIRED if ack_required else 0
        packet = {
            "type": "RREP",
            "sender": self.node_addr,
            "flags": flags,
            "prefix_size": 0,
            "hop_count": hop_count,
            "ttl": effective_ttl,
            "dest_addr": dest_addr,
            "dest_seq_num": dest_seq_num & 0xFFFFFFFF,
            "orig_addr": orig_addr,
            "lifetime": self.config.route_lifetime_sec,
        }
        self._send_packet_to_ip(next_hop_ip, packet)
        if ack_required:
            self.rrep_ack_manager.track(next_hop_ip, time.time(), self.config.rrep_ack_timeout_sec)

    def _send_rrep_ack(self, next_hop_ip: str) -> None:
        packet = {"type": "RREP-ACK", "sender": self.node_addr}
        self._send_packet_to_ip(next_hop_ip, packet)

    def _send_user_data(self, dest_addr: str, payload: str) -> str:
        packet = {
            "type": "DATA",
            "sender": self.node_addr,
            "orig_addr": self.node_addr,
            "dest_addr": dest_addr,
            "hop_count": 0,
            "ttl": self.config.rreq_ttl,
            "payload": payload,
        }
        now = time.time()
        route = self.route_manager.get_valid(dest_addr, now)
        if route is None:
            known = self.routing_table.get(dest_addr)
            seq_hint = known.dest_seq_num if known else 0
            self._queue_data_packet(dest_addr, packet)
            self._start_route_discovery(dest_addr, seq_hint)
            return f"无可用路由，已触发发现并缓存消息（目标={dest_addr}）"

        self._send_packet_to_ip(route.next_hop_ip, packet)
        route.expires_at = now + self.config.route_lifetime_sec
        return f"消息已发送，下一跳={route.next_hop_ip}"

    def _touch_neighbor(self, neighbor_addr: str, neighbor_ip: str) -> None:
        if neighbor_addr == self.node_addr or neighbor_ip == self.node_addr:
            return
        now = time.time()
        self.neighbor_manager.touch(neighbor_addr, neighbor_ip, now)
        self.route_manager.upsert_connected(neighbor_addr, neighbor_ip, now, self.config.route_lifetime_sec)

    def _process_data(self, packet: dict, sender_ip: str) -> None:
        sender = packet.get("sender")
        orig_addr = packet.get("orig_addr")
        dest_addr = packet.get("dest_addr")
        payload = packet.get("payload", "")
        ttl = int(packet.get("ttl", 0))
        hop_count = int(packet.get("hop_count", 0))

        if not sender or not orig_addr or not dest_addr:
            return
        if ttl <= 0:
            return

        self._touch_neighbor(sender, sender_ip)

        if dest_addr == self.node_addr:
            self.message_box.append(
                DataMessage(src_addr=orig_addr, dest_addr=dest_addr, payload=str(payload), arrived_ts=time.time())
            )
            return

        route = self.route_manager.get_valid(dest_addr, time.time())
        if route is None:
            deferred = self._build_forward_data_packet(packet)
            if deferred is not None:
                self._queue_data_packet(dest_addr, deferred)
            self._start_route_discovery(dest_addr)
            return

        self.error_manager.add_precursor(dest_addr, sender_ip)
        fwd = self._build_forward_data_packet(packet)
        if fwd is None:
            return
        self._send_packet_to_ip(route.next_hop_ip, fwd)
        route.expires_at = time.time() + self.config.route_lifetime_sec

    def _process_rreq(self, packet: dict, sender_ip: str) -> None:
        if self.node_status != "ACTIVE":
            return

        sender = packet.get("sender")
        orig_addr = packet.get("orig_addr")
        dest_addr = packet.get("dest_addr")
        if not sender or not orig_addr or not dest_addr:
            return

        ttl = int(packet.get("ttl", 0))
        if ttl <= 0:
            return

        hop_count = int(packet.get("hop_count", 0))
        flags = int(packet.get("flags", 0)) & 0xFF
        if flags & RREQ_FLAG_JOIN:
            return
        is_unknown_seq = bool(flags & RREQ_FLAG_UNKNOWN_SEQ)
        dest_only = bool(flags & RREQ_FLAG_DEST_ONLY)
        gratuitous = bool(flags & RREQ_FLAG_GRATUITOUS)
        is_local_repair = bool(flags & RREQ_FLAG_REPAIR)

        rreq_id = int(packet.get("rreq_id", 0))
        orig_seq_num = int(packet.get("orig_seq_num", 0))
        dest_seq_num = 0 if is_unknown_seq else int(packet.get("dest_seq_num", 0))

        self._touch_neighbor(sender, sender_ip)

        key = (orig_addr, rreq_id)
        now = time.time()
        if self.duplicate_set.has_valid(key, now):
            return
        self.duplicate_set.remember(key, now + self.config.path_discovery_timeout_sec)

        reverse_route = RouteEntry(
            dest_addr=orig_addr,
            next_hop=sender,
            next_hop_ip=sender_ip,
            hop_count=hop_count + 1,
            dest_seq_num=orig_seq_num,
            valid=True,
            route_state="VALID",
            expires_at=now + self.config.route_lifetime_sec,
        )
        self.route_manager.upsert_discovered(reverse_route)

        if dest_addr == self.node_addr:
            if is_unknown_seq:
                self.seq_num = (self.seq_num + 1) & 0xFFFFFFFF
            else:
                self.seq_num = (max(self.seq_num, dest_seq_num) + 1) & 0xFFFFFFFF
            self._send_rrep(orig_addr, sender_ip, self.node_addr, self.seq_num, 0, ttl=self.config.rreq_ttl)
            return

        known = self.route_manager.get_valid(dest_addr, now)
        can_intermediate_reply = (not dest_only) and (not is_local_repair)
        if can_intermediate_reply and known and (
            is_unknown_seq
            or known.dest_seq_num == dest_seq_num
            or is_seq_newer(known.dest_seq_num, dest_seq_num)
        ):
            self._send_rrep(
                orig_addr,
                sender_ip,
                dest_addr,
                known.dest_seq_num,
                known.hop_count,
                ttl=self.config.rreq_ttl,
            )
            if gratuitous:
                route_to_origin = self.route_manager.get_valid(orig_addr, now)
                if route_to_origin is not None:
                    self._send_rrep(
                        orig_addr=dest_addr,
                        next_hop_ip=known.next_hop_ip,
                        dest_addr=orig_addr,
                        dest_seq_num=orig_seq_num,
                        hop_count=route_to_origin.hop_count,
                        ttl=self.config.rreq_ttl,
                    )
            return

        fwd = dict(packet)
        fwd["sender"] = self.node_addr
        fwd["hop_count"] = (hop_count + 1) & 0xFF
        fwd["ttl"] = (ttl - 1) & 0xFF
        self._broadcast_to_neighbors(fwd, exclude_node=sender_ip)

    def _process_rrep(self, packet: dict, sender_ip: str) -> None:
        sender = packet.get("sender")
        dest_addr = packet.get("dest_addr")
        orig_addr = packet.get("orig_addr")
        if not sender or not dest_addr or not orig_addr:
            return

        self._touch_neighbor(sender, sender_ip)
        flags = int(packet.get("flags", 0))
        if flags & RREP_FLAG_ACK_REQUIRED:
            self._send_rrep_ack(sender_ip)

        hop_count = int(packet.get("hop_count", 0))
        ttl = int(packet.get("ttl", 0))
        dest_seq_num = int(packet.get("dest_seq_num", 0))
        lifetime = int(packet.get("lifetime", self.config.route_lifetime_sec))
        now = time.time()
        if ttl <= 0:
            return

        # HELLO 本质：TTL=1 的特殊 RREP（RFC 3561）
        if ttl == 1 and hop_count == 0 and dest_addr == sender and orig_addr == sender:
            return

        new_route = RouteEntry(
            dest_addr=dest_addr,
            next_hop=sender,
            next_hop_ip=sender_ip,
            hop_count=hop_count + 1,
            dest_seq_num=dest_seq_num,
            valid=True,
            route_state="VALID",
            expires_at=now + max(1, lifetime),
        )
        self.route_manager.upsert_discovered(new_route)
        self.local_repair_manager.complete(dest_addr)

        if orig_addr == self.node_addr:
            self.discovery_manager.clear(dest_addr)
            self._flush_pending_data(dest_addr)
            return

        reverse = self.route_manager.get_valid(orig_addr, now)
        if reverse is None:
            return

        self.error_manager.add_precursor(dest_addr, reverse.next_hop_ip)
        self._send_rrep(
            orig_addr=orig_addr,
            next_hop_ip=reverse.next_hop_ip,
            dest_addr=dest_addr,
            dest_seq_num=dest_seq_num,
            hop_count=(hop_count + 1) & 0xFF,
            ttl=max(1, ttl - 1),
            require_ack=self.config.rrep_ack_enabled,
        )
        self._flush_pending_data(dest_addr)

    def _process_rrep_ack(self, packet: dict, sender_ip: str) -> None:
        sender = packet.get("sender")
        if not sender:
            return
        self._touch_neighbor(sender, sender_ip)
        self.rrep_ack_manager.acknowledge(sender_ip)

    def _process_rerr(self, packet: dict, sender_ip: str) -> None:
        sender = packet.get("sender")
        unreachable = packet.get("unreachable", [])
        if not sender or not isinstance(unreachable, list):
            return

        self._touch_neighbor(sender, sender_ip)

        now = time.time()
        changed: list[dict] = []
        for item in unreachable:
            if not isinstance(item, dict):
                continue
            dest_addr = item.get("dest_addr")
            if not dest_addr:
                continue
            dest_seq = int(item.get("dest_seq_num", 0))
            route = self.routing_table.get(dest_addr)
            if route is None:
                continue
            if route.next_hop != sender:
                continue
            invalid = self.route_manager.invalidate(dest_addr, dest_seq, now, self.config.path_discovery_timeout_sec)
            if invalid:
                changed.append({"dest_addr": invalid.dest_addr, "dest_seq_num": invalid.dest_seq_num})

        if changed:
            to_rerr = self._maybe_start_local_repair(changed, allow_repair=True)
            if to_rerr:
                self._send_rerr(to_rerr, exclude_node=sender_ip)

    def _handle_overlay_packet(self, raw: bytes, sender_ip: str) -> None:
        packet = decode_packet(raw)
        if packet is None:
            return

        msg_type = packet.get("type")
        if msg_type == "DATA":
            self._process_data(packet, sender_ip)
        elif msg_type == "RREQ":
            self._process_rreq(packet, sender_ip)
        elif msg_type == "RREP":
            self._process_rrep(packet, sender_ip)
        elif msg_type == "RERR":
            self._process_rerr(packet, sender_ip)
        elif msg_type == "RREP-ACK":
            self._process_rrep_ack(packet, sender_ip)

    def _run_housekeeping(self) -> None:
        now = time.time()

        if self.node_status == "ACTIVE" and (now - self.last_hello_ts >= self.config.hello_interval_sec):
            self._send_hello()

        self.duplicate_set.cleanup(now)

        stale_neighbors = self.neighbor_manager.stale_neighbors(now, self.config.hello_timeout_sec)
        stale_neighbors.extend(self.rrep_ack_manager.timed_out_neighbors(now))
        stale_neighbors = list(set(stale_neighbors))
        for neighbor in stale_neighbors:
            self.neighbor_manager.remove(neighbor)
            self.error_manager.remove_precursor(neighbor)

        unreachable = []
        for neighbor in stale_neighbors:
            invalidated = self.route_manager.invalidate_via_next_hop(
                neighbor, now, self.config.path_discovery_timeout_sec
            )
            unreachable.extend(invalidated)

        self.route_manager.expire_routes(now)

        for dest_addr in self.discovery_manager.ready_destinations(now, self.config.rreq_retries):
            known = self.routing_table.get(dest_addr)
            seq_hint = known.dest_seq_num if known else 0
            self._start_route_discovery(dest_addr, seq_hint)

        for dest_addr in self.discovery_manager.exhausted_destinations(self.config.rreq_retries):
            self.discovery_manager.clear(dest_addr)
            self._drop_pending_data(dest_addr)

        if unreachable:
            to_rerr = self._maybe_start_local_repair(unreachable, allow_repair=True)
            if to_rerr:
                self._send_rerr(to_rerr)

        # 本地修复超时后的条目不再二次修复，直接 RERR
        timeout_unreachable: list[dict] = []
        timed_out_repairs = self.local_repair_manager.timed_out(now)
        for state in timed_out_repairs:
            timeout_unreachable.append({"dest_addr": state.dest_addr, "dest_seq_num": state.dest_seq_num})
            self._drop_pending_data(state.dest_addr)
        if timeout_unreachable:
            self._send_rerr(timeout_unreachable)

    def run(self) -> None:
        self._init_logger()
        self._bootstrap_neighbors()

        self.overlay_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.overlay_sock.bind((self.config.bind_ip, self.config.overlay_port))
        self.overlay_sock.setblocking(False)
        self.overlay_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.overlay_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.control_sock.bind((self.config.control_bind_ip, self.config.control_port))
        self.control_sock.setblocking(False)
        self.control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        sockets = [self.overlay_sock, self.control_sock]

        try:
            while not self._stop_event.is_set():
                readable, _, _ = select.select(sockets, [], [], 1.0)

                for sock in readable:
                    if sock is self.overlay_sock:
                        raw, remote_addr = self.overlay_sock.recvfrom(8192)
                        self._handle_overlay_packet(raw, remote_addr[0])
                    elif sock is self.control_sock:
                        raw, remote_addr = self.control_sock.recvfrom(8192)
                        command_text = raw.decode("utf-8", errors="ignore")
                        result = process_control_command(self, command_text)
                        self.control_sock.sendto(result.encode("utf-8"), remote_addr)

                self._run_housekeeping()

        finally:
            if self.overlay_sock:
                self.overlay_sock.close()
            if self.control_sock:
                self.control_sock.close()
