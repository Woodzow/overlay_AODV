"""RREP-ACK 等待状态管理器。

用途：
1) 发送 RREP 且要求 ACK 后，记录下一跳与超时截止时间
2) 收到 RREP-ACK 后清除等待状态
3) 超时后返回可疑邻居，供协议层触发路由失效处理
"""


class RrepAckManager:
    def __init__(self):
        # 结构示例：{"10.0.0.2": 1710000123.456}
        self._pending: dict[str, float] = {}

    def track(self, next_hop_ip: str, now: float, timeout_sec: int) -> None:
        if not next_hop_ip:
            return
        self._pending[next_hop_ip] = now + max(1, timeout_sec)

    def acknowledge(self, neighbor_ip: str) -> bool:
        if neighbor_ip in self._pending:
            self._pending.pop(neighbor_ip, None)
            return True
        return False

    def timed_out_neighbors(self, now: float) -> list[str]:
        failed: list[str] = []
        for ip, deadline in list(self._pending.items()):
            if deadline <= now:
                failed.append(ip)
                self._pending.pop(ip, None)
        return failed

    def snapshot(self) -> dict[str, float]:
        return dict(self._pending)
