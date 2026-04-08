from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

from video_transfer_common import (
    ControlClient,
    InboxCursor,
    b64decode_bytes,
    bytes_sha256,
    decode_envelope,
    encode_envelope,
    file_sha256,
)


@dataclass
class TransferState:
    transfer_id: str
    src_addr: str
    file_name: str
    file_size: int
    total_chunks: int
    file_sha256: str
    part_path: Path
    final_path: Path
    next_chunk_id: int = 0
    bytes_written: int = 0
    eof_received: bool = False


class Receiver:
    def __init__(self, output_dir: Path, client: ControlClient, inbox: InboxCursor):
        self.output_dir = output_dir
        self.client = client
        self.inbox = inbox
        self.transfers: dict[str, TransferState] = {}
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def send_ack(self, dest_ip: str, transfer_id: str, ack_for: str, status: str, **fields: object) -> None:
        payload = encode_envelope('ack', transfer_id=transfer_id, ack_for=ack_for, status=status, **fields)
        response = self.client.send_message(dest_ip, payload)
        print(f'ack {ack_for} -> {dest_ip}: {response}', flush=True)

    def build_final_path(self, file_name: str) -> Path:
        base_path = self.output_dir / file_name
        if not base_path.exists():
            return base_path
        stem = base_path.stem
        suffix = base_path.suffix
        for index in range(1, 1000):
            candidate = base_path.with_name(f'{stem}_{index}{suffix}')
            if not candidate.exists():
                return candidate
        raise RuntimeError(f'could not allocate output path for {file_name}')

    def handle_meta(self, src_addr: str, envelope: dict[str, object]) -> None:
        transfer_id = str(envelope['transfer_id'])
        if transfer_id in self.transfers:
            self.send_ack(src_addr, transfer_id, 'meta', 'ok')
            return

        file_name = str(envelope['file_name'])
        final_path = self.build_final_path(file_name)
        part_path = final_path.with_suffix(final_path.suffix + '.part')
        state = TransferState(
            transfer_id=transfer_id,
            src_addr=src_addr,
            file_name=file_name,
            file_size=int(envelope['file_size']),
            total_chunks=int(envelope['total_chunks']),
            file_sha256=str(envelope['file_sha256']),
            part_path=part_path,
            final_path=final_path,
        )
        part_path.parent.mkdir(parents=True, exist_ok=True)
        with part_path.open('wb'):
            pass
        self.transfers[transfer_id] = state
        print(f'meta received transfer_id={transfer_id} file={file_name} total_chunks={state.total_chunks}', flush=True)
        self.send_ack(src_addr, transfer_id, 'meta', 'ok')

    def handle_chunk(self, src_addr: str, envelope: dict[str, object]) -> None:
        transfer_id = str(envelope['transfer_id'])
        state = self.transfers.get(transfer_id)
        if state is None:
            self.send_ack(src_addr, transfer_id, 'chunk', 'error', detail='missing meta')
            return

        chunk_id = int(envelope['chunk_id'])
        if chunk_id < state.next_chunk_id:
            self.send_ack(src_addr, transfer_id, 'chunk', 'ok', chunk_id=chunk_id, duplicate=True)
            return
        if chunk_id > state.next_chunk_id:
            self.send_ack(
                src_addr,
                transfer_id,
                'chunk',
                'error',
                chunk_id=chunk_id,
                detail=f'expected chunk {state.next_chunk_id}',
            )
            return

        raw_chunk = b64decode_bytes(str(envelope['payload_b64']))
        expected_sha = str(envelope['chunk_sha256'])
        actual_sha = bytes_sha256(raw_chunk)
        if actual_sha != expected_sha:
            self.send_ack(src_addr, transfer_id, 'chunk', 'error', chunk_id=chunk_id, detail='chunk sha mismatch')
            return

        with state.part_path.open('ab') as handle:
            handle.write(raw_chunk)
        state.next_chunk_id += 1
        state.bytes_written += len(raw_chunk)
        print(f'chunk received transfer_id={transfer_id} chunk={chunk_id + 1}/{state.total_chunks}', flush=True)
        self.send_ack(src_addr, transfer_id, 'chunk', 'ok', chunk_id=chunk_id)

    def handle_eof(self, src_addr: str, envelope: dict[str, object]) -> None:
        transfer_id = str(envelope['transfer_id'])
        state = self.transfers.get(transfer_id)
        if state is None:
            self.send_ack(src_addr, transfer_id, 'eof', 'error', detail='missing meta')
            return

        state.eof_received = True
        if state.next_chunk_id != state.total_chunks:
            self.send_ack(
                src_addr,
                transfer_id,
                'eof',
                'error',
                detail=f'incomplete chunks {state.next_chunk_id}/{state.total_chunks}',
            )
            return
        if state.bytes_written != state.file_size:
            self.send_ack(
                src_addr,
                transfer_id,
                'eof',
                'error',
                detail=f'size mismatch {state.bytes_written}/{state.file_size}',
            )
            return
        actual_file_sha = file_sha256(state.part_path)
        if actual_file_sha != state.file_sha256:
            self.send_ack(src_addr, transfer_id, 'eof', 'error', detail='file sha mismatch')
            return

        state.part_path.replace(state.final_path)
        print(f'transfer complete transfer_id={transfer_id} saved={state.final_path}', flush=True)
        self.send_ack(src_addr, transfer_id, 'eof', 'complete', output_path=str(state.final_path))
        self.transfers.pop(transfer_id, None)

    def process_once(self) -> None:
        for item in self.inbox.read_new():
            envelope = decode_envelope(item.payload)
            if envelope is None:
                continue
            kind = envelope.get('kind')
            if kind == 'meta':
                self.handle_meta(item.src_addr, envelope)
            elif kind == 'chunk':
                self.handle_chunk(item.src_addr, envelope)
            elif kind == 'eof':
                self.handle_eof(item.src_addr, envelope)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Receive a video file over the AODV overlay and rebuild it locally.')
    parser.add_argument('--output-dir', default='received_videos', help='Directory used for rebuilt video files.')
    parser.add_argument('--control-ip', default='127.0.0.1', help='Local AODV control endpoint IP.')
    parser.add_argument('--control-port', type=int, default=5100, help='Local AODV control endpoint UDP port.')
    parser.add_argument('--poll-interval-sec', type=float, default=0.3, help='Inbox polling interval.')
    parser.add_argument('--keep-inbox', action='store_true', help='Do not clear local message inbox on startup.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = ControlClient(control_ip=args.control_ip, control_port=args.control_port)
    inbox = InboxCursor(client)
    if args.keep_inbox:
        inbox.skip_existing()
    else:
        print(client.clear_messages(), flush=True)

    receiver = Receiver(output_dir=Path(args.output_dir).expanduser().resolve(), client=client, inbox=inbox)
    print(f'listening for video files, output_dir={receiver.output_dir}', flush=True)
    while True:
        receiver.process_once()
        time.sleep(args.poll_interval_sec)


if __name__ == '__main__':
    raise SystemExit(main())
