"""AODV 错误传播管理器。"""


class ErrorManager:
    def __init__(self):
        self.precursors: dict[str, set[str]] = {}
        self._last_rerr_emit_ts: dict[tuple[tuple[str, int], ...], float] = {}

    def add_precursor(self, dest_addr: str, precursor_addr: str) -> None:
        if not dest_addr or not precursor_addr:
            return
        self.precursors.setdefault(dest_addr, set()).add(precursor_addr)

    def remove_precursor(self, precursor_addr: str) -> None:
        for _, values in self.precursors.items():
            values.discard(precursor_addr)
        for key in list(self.precursors.keys()):
            if not self.precursors[key]:
                self.precursors.pop(key, None)

    def remove_dest(self, dest_addr: str) -> None:
        self.precursors.pop(dest_addr, None)

    def targets_for_unreachable(self, unreachable: list[dict]) -> set[str]:
        targets: set[str] = set()
        for item in unreachable:
            dest_addr = item.get("dest_addr")
            if not dest_addr:
                continue
            targets.update(self.precursors.get(dest_addr, set()))
        return targets

    def normalize_unreachable(self, unreachable: list[dict], max_items: int = 16) -> list[dict]:
        merged: dict[str, int] = {}
        for item in unreachable:
            if not isinstance(item, dict):
                continue
            dest = item.get("dest_addr")
            if not dest:
                continue
            seq = int(item.get("dest_seq_num", 0)) & 0xFFFFFFFF
            merged[dest] = max(merged.get(dest, 0), seq)
        normalized = [{"dest_addr": dest, "dest_seq_num": seq} for dest, seq in sorted(merged.items())]
        return normalized[: max(1, int(max_items))]

    def should_emit_rerr(self, unreachable: list[dict], now: float, rate_limit_sec: int) -> bool:
        signature = tuple((item["dest_addr"], int(item["dest_seq_num"])) for item in unreachable if "dest_addr" in item)
        if not signature:
            return False
        last = self._last_rerr_emit_ts.get(signature, 0.0)
        if now - last < max(0, int(rate_limit_sec)):
            return False
        self._last_rerr_emit_ts[signature] = now
        return True
