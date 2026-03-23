"""AODV 去重集合管理器。"""

from dataclasses import dataclass


@dataclass
class DuplicateRecord:
    key: tuple[str, int]
    expires_at: float
    retransmitted: bool = False


class DuplicateSet:
    def __init__(self):
        self._records: dict[tuple[str, int], DuplicateRecord] = {}

    def has_valid(self, key: tuple[str, int], now: float) -> bool:
        rec = self._records.get(key)
        return bool(rec and rec.expires_at > now)

    def remember(self, key: tuple[str, int], expires_at: float) -> None:
        self._records[key] = DuplicateRecord(key=key, expires_at=expires_at)

    def mark_retransmitted(self, key: tuple[str, int]) -> None:
        rec = self._records.get(key)
        if rec:
            rec.retransmitted = True

    def was_retransmitted(self, key: tuple[str, int]) -> bool:
        rec = self._records.get(key)
        return bool(rec and rec.retransmitted)

    def cleanup(self, now: float) -> None:
        for key, rec in list(self._records.items()):
            if rec.expires_at <= now:
                self._records.pop(key, None)
