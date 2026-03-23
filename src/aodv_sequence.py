"""AODV 序列号比较工具。"""

MAX_SEQ_NUM = 0xFFFFFFFF
HALF_SEQ_RANGE = (MAX_SEQ_NUM + 1) // 2


def is_seq_newer(candidate: int, current: int) -> bool:
    """判断 candidate 是否比 current 更新（支持回绕）。"""
    candidate &= MAX_SEQ_NUM
    current &= MAX_SEQ_NUM
    if candidate == current:
        return False

    forward = (candidate - current) & MAX_SEQ_NUM
    return 0 < forward < HALF_SEQ_RANGE
