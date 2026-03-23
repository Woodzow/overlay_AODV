"""AODV 本地修复（Local Repair）状态管理器。"""

from dataclasses import dataclass


@dataclass
class LocalRepairState:
    dest_addr: str
    dest_seq_num: int
    started_at: float
    deadline_at: float


class LocalRepairManager:
    def __init__(self):
        # 结构示例：{"10.0.0.9": LocalRepairState(...)}
        self._states: dict[str, LocalRepairState] = {}

    def start(self, dest_addr: str, dest_seq_num: int, now: float, wait_sec: int) -> None:
        self._states[dest_addr] = LocalRepairState(
            dest_addr=dest_addr,
            dest_seq_num=dest_seq_num,
            started_at=now,
            deadline_at=now + max(1, wait_sec),
        )

    def is_repairing(self, dest_addr: str) -> bool:
        return dest_addr in self._states

    def complete(self, dest_addr: str) -> None:
        self._states.pop(dest_addr, None)

    def timed_out(self, now: float) -> list[LocalRepairState]:
        failed: list[LocalRepairState] = []
        for dest_addr, state in list(self._states.items()):
            if state.deadline_at <= now:
                failed.append(state)
                self._states.pop(dest_addr, None)
        return failed

    def snapshot(self) -> dict[str, LocalRepairState]:
        return dict(self._states)
