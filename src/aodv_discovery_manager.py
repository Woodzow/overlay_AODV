"""AODV 路由发现状态管理器。

用于管理每个目的地址的 RREQ 发现状态：
1) 重试次数
2) 下一次可发送时间
3) 扩环搜索 TTL（Expanding Ring Search）
"""

from dataclasses import dataclass


@dataclass
class DiscoveryState:
    """单个目的地址的路由发现状态。"""

    attempts: int
    next_ttl: int
    next_retry_at: float


class DiscoveryManager:
    """管理所有目的地址的发现状态。"""

    def __init__(self):
        # 结构示例：
        # {
        #   "10.0.0.8": DiscoveryState(attempts=1, next_ttl=4, next_retry_at=1710000100.0)
        # }
        self._states: dict[str, DiscoveryState] = {}

    def should_send(self, dest_addr: str, now: float, max_retries: int) -> bool:
        state = self._states.get(dest_addr)
        if state is None:
            return True
        if state.attempts >= max_retries:
            return False
        return now >= state.next_retry_at

    def current_ttl(self, dest_addr: str, ttl_start: int, ttl_increment: int, ttl_threshold: int, max_ttl: int) -> int:
        state = self._states.get(dest_addr)
        if state is None:
            return max(1, min(ttl_start, max_ttl))

        ttl = state.next_ttl
        if ttl < ttl_threshold:
            ttl = min(ttl + ttl_increment, ttl_threshold)
        else:
            ttl = max_ttl
        return max(1, min(ttl, max_ttl))

    def mark_sent(self, dest_addr: str, ttl_used: int, now: float, retry_wait_sec: int) -> None:
        state = self._states.get(dest_addr)
        attempts = 1 if state is None else state.attempts + 1
        self._states[dest_addr] = DiscoveryState(
            attempts=attempts,
            next_ttl=ttl_used,
            next_retry_at=now + max(1, retry_wait_sec),
        )

    def ready_destinations(self, now: float, max_retries: int) -> list[str]:
        ready: list[str] = []
        for dest_addr, state in self._states.items():
            if state.attempts >= max_retries:
                continue
            if now >= state.next_retry_at:
                ready.append(dest_addr)
        return ready

    def exhausted_destinations(self, max_retries: int) -> list[str]:
        failed: list[str] = []
        for dest_addr, state in self._states.items():
            if state.attempts >= max_retries:
                failed.append(dest_addr)
        return failed

    def clear(self, dest_addr: str) -> None:
        self._states.pop(dest_addr, None)

    def snapshot(self) -> dict[str, DiscoveryState]:
        return dict(self._states)
