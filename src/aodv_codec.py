"""AODV 报文二进制编解码（RFC 3561 对齐增强版）。

实现约定：
1) 统一公共头：Version(1) + MsgType(1) + TotalLength(2)
2) 地址统一使用 IPv4 4 字节（二进制）编码
3) 字段命名尽量贴近 RFC 3561：
   - RREQ: orig_addr/dest_addr/orig_seq_num/dest_seq_num/rreq_id
   - RREP: orig_addr/dest_addr/dest_seq_num/lifetime
   - RERR: unreachable[{dest_addr, dest_seq_num}, ...]
4) 为覆盖网络转发需要，消息体保留 sender（上一跳发送者 IP）

字典输入示例：
{
  "type": "RREQ",
  "sender": "10.0.0.1",
  "flags": 0,
  "hop_count": 0,
  "ttl": 8,
  "rreq_id": 12,
  "dest_addr": "10.0.0.7",
  "dest_seq_num": 20,
  "orig_addr": "10.0.0.1",
  "orig_seq_num": 88
}
"""

import socket
import struct
from typing import Any

PROTOCOL_VERSION = 1

TYPE_RREQ = 2
TYPE_RREP = 3
TYPE_RERR = 4
TYPE_DATA = 5
TYPE_RREP_ACK = 6

# RREQ flags（RFC 3561 Section 5.1）
# J 位（0x80）用于组播扩展，本项目不支持组播，仅识别后丢弃。
RREQ_FLAG_JOIN = 0x80
RREQ_FLAG_REPAIR = 0x40
RREQ_FLAG_GRATUITOUS = 0x20
RREQ_FLAG_DEST_ONLY = 0x10
RREQ_FLAG_UNKNOWN_SEQ = 0x08
RREQ_SUPPORTED_FLAG_MASK = (
    RREQ_FLAG_JOIN
    | RREQ_FLAG_REPAIR
    | RREQ_FLAG_GRATUITOUS
    | RREQ_FLAG_DEST_ONLY
    | RREQ_FLAG_UNKNOWN_SEQ
)

# RREP flags（RFC 3561 Section 5.2）
# A 位：要求下一跳返回 RREP-ACK
RREP_FLAG_ACK_REQUIRED = 0x40

TYPE_NAME_TO_CODE = {
    "RREQ": TYPE_RREQ,
    "RREP": TYPE_RREP,
    "RERR": TYPE_RERR,
    "DATA": TYPE_DATA,
    "RREP-ACK": TYPE_RREP_ACK,
}
TYPE_CODE_TO_NAME = {v: k for k, v in TYPE_NAME_TO_CODE.items()}

# 通用头（工程头，不直接对应 RFC 原文字段）：（这里是针对overlay进行的必要字段增加）
# Version(1) + MsgType(1) + TotalLength(2)
COMMON_HEADER_FMT = "!BBH"
COMMON_HEADER_LEN = struct.calcsize(COMMON_HEADER_FMT)


def _encode_ipv4(addr: str) -> bytes:
    try:
        return socket.inet_aton(addr)
    except OSError as exc:
        raise ValueError(f"非法 IPv4 地址: {addr}") from exc


def _decode_ipv4(raw: bytes) -> str:
    try:
        return socket.inet_ntoa(raw)
    except OSError:
        return ""


def _pack_common_header(msg_type_code: int, body_len: int) -> bytes:
    total_len = COMMON_HEADER_LEN + body_len
    return struct.pack(COMMON_HEADER_FMT, PROTOCOL_VERSION, msg_type_code, total_len)


# RREQ（RFC 3561 Section 5.1 对齐简化 + sender）:
# Sender(4) + Flags(1) + Reserved(1) + HopCount(1) + TTL(1)
# + RREQ_ID(4) + DestAddr(4) + DestSeqNum(4) + OrigAddr(4) + OrigSeqNum(4)
RREQ_FMT = "!4sBBBBI4sI4sI"
RREQ_LEN = struct.calcsize(RREQ_FMT)

# RREP（RFC 3561 Section 5.2 对齐简化 + sender）:
# Sender(4) + Flags(1) + PrefixSize(1) + HopCount(1) + TTL(1)
# + DestAddr(4) + DestSeqNum(4) + OrigAddr(4) + Lifetime(4)
RREP_FMT = "!4sBBBB4sI4sI"
RREP_LEN = struct.calcsize(RREP_FMT)

# RERR Header（RFC 3561 Section 5.3 对齐简化 + sender）:
# Sender(4) + Flags(1) + DestCount(1) + Reserved(2)
RERR_HEAD_FMT = "!4sBBH"
RERR_HEAD_LEN = struct.calcsize(RERR_HEAD_FMT)
# RERR item: UnreachableDest(4) + DestSeqNum(4)
RERR_ITEM_FMT = "!4sI"
RERR_ITEM_LEN = struct.calcsize(RERR_ITEM_FMT)

# DATA（工程业务消息，非 RFC 3561 标准消息类型）:
# Sender(4) + OrigAddr(4) + DestAddr(4) + HopCount(1) + TTL(1) + Reserved(2)
# + PayloadLen(2) + Payload(N)
DATA_HEAD_FMT = "!4s4s4sBBHH"
DATA_HEAD_LEN = struct.calcsize(DATA_HEAD_FMT)

# RREP-ACK（RFC 3561 Section 5.4 对齐 + sender）
# Sender(4) + Reserved(2)
RREP_ACK_FMT = "!4sH"
RREP_ACK_LEN = struct.calcsize(RREP_ACK_FMT)


def _encode_rreq(packet: dict[str, Any]) -> bytes:
    sender = _encode_ipv4(str(packet["sender"]))
    flags = int(packet.get("flags", 0)) & 0xFF
    if flags & (~RREQ_SUPPORTED_FLAG_MASK & 0xFF):
        raise ValueError("RREQ flags 包含未支持位")
    hop_count = int(packet.get("hop_count", 0)) & 0xFF
    ttl = int(packet.get("ttl", 0)) & 0xFF
    if ttl == 0:
        raise ValueError("RREQ ttl 不能为 0")
    rreq_id = int(packet["rreq_id"]) & 0xFFFFFFFF
    dest_addr = _encode_ipv4(str(packet["dest_addr"]))
    dest_seq_num = int(packet.get("dest_seq_num", 0)) & 0xFFFFFFFF
    orig_addr = _encode_ipv4(str(packet["orig_addr"]))
    orig_seq_num = int(packet.get("orig_seq_num", 0)) & 0xFFFFFFFF

    return struct.pack(
        RREQ_FMT,
        sender,
        flags,
        0,
        hop_count,
        ttl,
        rreq_id,
        dest_addr,
        dest_seq_num,
        orig_addr,
        orig_seq_num,
    )


def _encode_rrep(packet: dict[str, Any]) -> bytes:
    sender = _encode_ipv4(str(packet["sender"]))
    flags = int(packet.get("flags", 0)) & 0xFF
    prefix_size = int(packet.get("prefix_size", 0)) & 0xFF
    hop_count = int(packet.get("hop_count", 0)) & 0xFF
    ttl = int(packet.get("ttl", 0)) & 0xFF
    dest_addr = _encode_ipv4(str(packet["dest_addr"]))
    dest_seq_num = int(packet.get("dest_seq_num", 0)) & 0xFFFFFFFF
    orig_addr = _encode_ipv4(str(packet["orig_addr"]))
    lifetime = int(packet.get("lifetime", 0)) & 0xFFFFFFFF
    if ttl == 0:
        raise ValueError("RREP ttl 不能为 0")
    if prefix_size > 32:
        raise ValueError("RREP prefix_size 不能大于 32")

    return struct.pack(
        RREP_FMT,
        sender,
        flags,
        prefix_size,
        hop_count,
        ttl,
        dest_addr,
        dest_seq_num,
        orig_addr,
        lifetime,
    )


def _encode_rerr(packet: dict[str, Any]) -> bytes:
    sender = _encode_ipv4(str(packet["sender"]))
    flags = int(packet.get("flags", 0)) & 0xFF
    # 数据结构示例：
    # unreachable = [
    #   {"dest_addr": "10.0.0.8", "dest_seq_num": 101},
    #   {"dest_addr": "10.0.0.9", "dest_seq_num": 33},
    # ]
    unreachable = packet.get("unreachable", [])
    if not isinstance(unreachable, list):
        raise ValueError("RERR unreachable 必须是 list")
    if len(unreachable) > 255:
        raise ValueError("RERR unreachable 条目过多（>255）")

    chunks = [struct.pack(RERR_HEAD_FMT, sender, flags, len(unreachable), 0)]
    for item in unreachable:
        dest_addr = _encode_ipv4(str(item["dest_addr"]))
        dest_seq_num = int(item.get("dest_seq_num", 0)) & 0xFFFFFFFF
        chunks.append(struct.pack(RERR_ITEM_FMT, dest_addr, dest_seq_num))
    return b"".join(chunks)


def _encode_data(packet: dict[str, Any]) -> bytes:
    sender = _encode_ipv4(str(packet["sender"]))
    orig_addr = _encode_ipv4(str(packet["orig_addr"]))
    dest_addr = _encode_ipv4(str(packet["dest_addr"]))
    hop_count = int(packet.get("hop_count", 0)) & 0xFF
    ttl = int(packet.get("ttl", 0)) & 0xFF
    if ttl == 0:
        raise ValueError("DATA ttl 不能为 0")
    payload = str(packet.get("payload", "")).encode("utf-8")
    if len(payload) > 65535:
        raise ValueError("DATA payload 过长（>65535 字节）")

    head = struct.pack(DATA_HEAD_FMT, sender, orig_addr, dest_addr, hop_count, ttl, 0, len(payload))
    return head + payload


def _encode_rrep_ack(packet: dict[str, Any]) -> bytes:
    sender = _encode_ipv4(str(packet["sender"]))
    return struct.pack(RREP_ACK_FMT, sender, 0)


def _decode_rreq(body: bytes) -> dict[str, Any] | None:
    if len(body) != RREQ_LEN:
        return None
    (
        sender,
        flags,
        _reserved,
        hop_count,
        ttl,
        rreq_id,
        dest_addr,
        dest_seq_num,
        orig_addr,
        orig_seq_num,
    ) = struct.unpack(RREQ_FMT, body)

    if ttl == 0:
        return None

    return {
        "type": "RREQ",
        "sender": _decode_ipv4(sender),
        "flags": flags,
        "hop_count": hop_count,
        "ttl": ttl,
        "rreq_id": rreq_id,
        "dest_addr": _decode_ipv4(dest_addr),
        "dest_seq_num": dest_seq_num,
        "orig_addr": _decode_ipv4(orig_addr),
        "orig_seq_num": orig_seq_num,
    }


def _decode_rrep(body: bytes) -> dict[str, Any] | None:
    if len(body) != RREP_LEN:
        return None
    (
        sender,
        flags,
        prefix_size,
        hop_count,
        ttl,
        dest_addr,
        dest_seq_num,
        orig_addr,
        lifetime,
    ) = struct.unpack(RREP_FMT, body)
    if ttl == 0:
        return None
    if prefix_size > 32:
        return None

    return {
        "type": "RREP",
        "sender": _decode_ipv4(sender),
        "flags": flags,
        "prefix_size": prefix_size,
        "hop_count": hop_count,
        "ttl": ttl,
        "dest_addr": _decode_ipv4(dest_addr),
        "dest_seq_num": dest_seq_num,
        "orig_addr": _decode_ipv4(orig_addr),
        "lifetime": lifetime,
    }


def _decode_rerr(body: bytes) -> dict[str, Any] | None:
    if len(body) < RERR_HEAD_LEN:
        return None

    sender, flags, dest_count, _reserved = struct.unpack(RERR_HEAD_FMT, body[:RERR_HEAD_LEN])
    items_raw = body[RERR_HEAD_LEN:]

    if len(items_raw) != dest_count * RERR_ITEM_LEN:
        return None

    unreachable = []
    for i in range(dest_count):
        start = i * RERR_ITEM_LEN
        end = start + RERR_ITEM_LEN
        dest_addr, dest_seq_num = struct.unpack(RERR_ITEM_FMT, items_raw[start:end])
        unreachable.append({"dest_addr": _decode_ipv4(dest_addr), "dest_seq_num": dest_seq_num})

    return {
        "type": "RERR",
        "sender": _decode_ipv4(sender),
        "flags": flags,
        "unreachable": unreachable,
    }


def _decode_data(body: bytes) -> dict[str, Any] | None:
    if len(body) < DATA_HEAD_LEN:
        return None

    sender, orig_addr, dest_addr, hop_count, ttl, _reserved, payload_len = struct.unpack(
        DATA_HEAD_FMT, body[:DATA_HEAD_LEN]
    )
    payload_raw = body[DATA_HEAD_LEN:]
    if len(payload_raw) != payload_len:
        return None
    if ttl == 0:
        return None
    if payload_len > 65535:
        return None

    return {
        "type": "DATA",
        "sender": _decode_ipv4(sender),
        "orig_addr": _decode_ipv4(orig_addr),
        "dest_addr": _decode_ipv4(dest_addr),
        "hop_count": hop_count,
        "ttl": ttl,
        "payload": payload_raw.decode("utf-8", errors="ignore"),
    }


def _decode_rrep_ack(body: bytes) -> dict[str, Any] | None:
    if len(body) != RREP_ACK_LEN:
        return None
    sender, _reserved = struct.unpack(RREP_ACK_FMT, body)
    return {"type": "RREP-ACK", "sender": _decode_ipv4(sender)}


def encode_packet(packet: dict[str, Any]) -> bytes:
    """将上层字典编码为二进制报文。

    入参 packet 最小示例：
    - RREP(HELLO): {"type":"RREP", "sender":"10.0.0.1", "flags":0, "prefix_size":0,
                    "hop_count":0, "ttl":1, "dest_addr":"10.0.0.1",
                    "dest_seq_num":1, "orig_addr":"10.0.0.1", "lifetime":20}
    - DATA: {"type":"DATA", "sender":"10.0.0.1", "orig_addr":"10.0.0.1",
              "dest_addr":"10.0.0.2", "hop_count":0, "ttl":16, "payload":"hi"}
    """
    msg_type = str(packet.get("type", "")).upper()
    msg_code = TYPE_NAME_TO_CODE.get(msg_type)
    if msg_code is None:
        raise ValueError(f"不支持的报文类型: {msg_type}")

    if msg_type == "RREQ":
        body = _encode_rreq(packet)
    elif msg_type == "RREP":
        body = _encode_rrep(packet)
    elif msg_type == "RERR":
        body = _encode_rerr(packet)
    elif msg_type == "DATA":
        body = _encode_data(packet)
    elif msg_type == "RREP-ACK":
        body = _encode_rrep_ack(packet)
    else:
        raise ValueError(f"未实现报文类型: {msg_type}")

    return _pack_common_header(msg_code, len(body)) + body


def decode_packet(raw: bytes) -> dict[str, Any] | None:
    """将二进制报文解码为字典。

    返回 None 表示报文非法，常见原因：
    1) 版本号不匹配
    2) TotalLength 与实际字节数不一致
    3) 各消息体长度/字段校验不通过（例如 ttl=0）
    """
    if len(raw) < COMMON_HEADER_LEN:
        return None

    version, msg_code, total_len = struct.unpack(COMMON_HEADER_FMT, raw[:COMMON_HEADER_LEN])
    if version != PROTOCOL_VERSION:
        return None
    if total_len != len(raw):
        return None

    body = raw[COMMON_HEADER_LEN:]
    msg_type = TYPE_CODE_TO_NAME.get(msg_code)
    if msg_type is None:
        return None

    if msg_type == "RREQ":
        return _decode_rreq(body)
    if msg_type == "RREP":
        return _decode_rrep(body)
    if msg_type == "RERR":
        return _decode_rerr(body)
    if msg_type == "DATA":
        return _decode_data(body)
    if msg_type == "RREP-ACK":
        return _decode_rrep_ack(body)
    return None
