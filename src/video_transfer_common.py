from __future__ import annotations

import base64
import hashlib
import json
import socket
from dataclasses import dataclass
from pathlib import Path

APP_NAME = 'video_file'
APP_VERSION = 1
MESSAGE_HEADER = 'Source  Destination  Payload'
MESSAGE_DIVIDER = '----------------------------'


@dataclass(frozen=True)
class InboxMessage:
    src_addr: str
    dest_addr: str
    payload: str


class ControlClient:
    def __init__(self, control_ip: str = '127.0.0.1', control_port: int = 5100, timeout_sec: float = 3.0):
        self.control_ip = control_ip
        self.control_port = int(control_port)
        self.timeout_sec = float(timeout_sec)

    def send_command(self, command: str) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(self.timeout_sec)
            sock.sendto(command.encode('utf-8'), (self.control_ip, self.control_port))
            data, _ = sock.recvfrom(65535)
            return data.decode('utf-8', errors='ignore')
        finally:
            sock.close()

    def send_message(self, dest_ip: str, payload: str) -> str:
        return self.send_command(f'SEND_MESSAGE:{dest_ip}:{payload}')

    def show_messages(self) -> list[InboxMessage]:
        return parse_message_box(self.send_command('SHOW_MESSAGES'))

    def clear_messages(self) -> str:
        return self.send_command('CLEAR_MESSAGES')


class InboxCursor:
    def __init__(self, client: ControlClient):
        self.client = client
        self._offset = 0

    def skip_existing(self) -> None:
        self._offset = len(self.client.show_messages())

    def clear(self) -> None:
        self.client.clear_messages()
        self._offset = 0

    def read_new(self) -> list[InboxMessage]:
        items = self.client.show_messages()
        if self._offset > len(items):
            self._offset = 0
        new_items = items[self._offset :]
        self._offset = len(items)
        return new_items


def parse_message_box(raw_text: str) -> list[InboxMessage]:
    lines = [line.rstrip('\r') for line in raw_text.splitlines()]
    items: list[InboxMessage] = []
    for line in lines:
        stripped = line.strip()
        if (not stripped) or stripped == MESSAGE_HEADER or stripped == MESSAGE_DIVIDER:
            continue
        parts = stripped.split(None, 2)
        if len(parts) < 3:
            continue
        items.append(InboxMessage(src_addr=parts[0], dest_addr=parts[1], payload=parts[2]))
    return items


def encode_envelope(kind: str, **fields: object) -> str:
    payload = {'app': APP_NAME, 'version': APP_VERSION, 'kind': kind}
    payload.update(fields)
    return json.dumps(payload, ensure_ascii=True, separators=(',', ':'))


def decode_envelope(payload_text: str) -> dict[str, object] | None:
    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get('app') != APP_NAME:
        return None
    return data


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def b64encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def b64decode_bytes(text: str) -> bytes:
    return base64.b64decode(text.encode('ascii'))
