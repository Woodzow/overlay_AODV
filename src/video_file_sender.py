from __future__ import annotations

import argparse
import math
import time
import uuid
from pathlib import Path

from video_transfer_common import (
    ControlClient,
    InboxCursor,
    b64encode_bytes,
    bytes_sha256,
    decode_envelope,
    encode_envelope,
    file_sha256,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Send a video file over the AODV overlay using chunked messages.')
    parser.add_argument('--file', required=True, help='Path to the local video file to send.')
    parser.add_argument('--dest-ip', required=True, help='Destination node IP address.')
    parser.add_argument('--control-ip', default='127.0.0.1', help='Local AODV control endpoint IP.')
    parser.add_argument('--control-port', type=int, default=5100, help='Local AODV control endpoint UDP port.')
    parser.add_argument('--chunk-size', type=int, default=700, help='Raw bytes per application chunk before base64.')
    parser.add_argument('--ack-timeout-sec', type=float, default=8.0, help='Seconds to wait for each application ACK.')
    parser.add_argument('--poll-interval-sec', type=float, default=0.3, help='Inbox polling interval while waiting for ACKs.')
    parser.add_argument('--max-retries', type=int, default=5, help='Max retries for each meta/chunk/eof message.')
    parser.add_argument('--keep-inbox', action='store_true', help='Do not clear local message inbox before sending.')
    return parser.parse_args()


def wait_for_ack(
    inbox: InboxCursor,
    transfer_id: str,
    ack_for: str,
    ack_timeout_sec: float,
    poll_interval_sec: float,
    chunk_id: int | None = None,
) -> dict[str, object] | None:
    deadline = time.time() + ack_timeout_sec
    while time.time() < deadline:
        for item in inbox.read_new():
            envelope = decode_envelope(item.payload)
            if envelope is None:
                continue
            if envelope.get('kind') != 'ack':
                continue
            if envelope.get('transfer_id') != transfer_id:
                continue
            if envelope.get('ack_for') != ack_for:
                continue
            if chunk_id is not None and int(envelope.get('chunk_id', -1)) != chunk_id:
                continue
            return envelope
        time.sleep(poll_interval_sec)
    return None


def send_with_retry(
    client: ControlClient,
    inbox: InboxCursor,
    dest_ip: str,
    payload: str,
    transfer_id: str,
    ack_for: str,
    ack_timeout_sec: float,
    poll_interval_sec: float,
    max_retries: int,
    chunk_id: int | None = None,
) -> dict[str, object]:
    last_response = ''
    for attempt in range(1, max_retries + 1):
        last_response = client.send_message(dest_ip, payload)
        print(f'[{ack_for}] attempt={attempt} response={last_response}', flush=True)
        ack = wait_for_ack(
            inbox=inbox,
            transfer_id=transfer_id,
            ack_for=ack_for,
            ack_timeout_sec=ack_timeout_sec,
            poll_interval_sec=poll_interval_sec,
            chunk_id=chunk_id,
        )
        if ack is not None:
            status = str(ack.get('status', 'ok'))
            if status not in {'ok', 'complete'}:
                raise RuntimeError(f'application ack indicates failure: {ack}')
            return ack
    raise TimeoutError(
        f'no application ack for transfer_id={transfer_id} ack_for={ack_for} chunk_id={chunk_id}; '
        f'last_response={last_response}'
    )


def main() -> int:
    args = parse_args()
    source_path = Path(args.file).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f'file not found: {source_path}')
    if args.chunk_size <= 0:
        raise ValueError('--chunk-size must be positive')

    transfer_id = uuid.uuid4().hex
    client = ControlClient(control_ip=args.control_ip, control_port=args.control_port)
    inbox = InboxCursor(client)

    if args.keep_inbox:
        inbox.skip_existing()
    else:
        print(client.clear_messages(), flush=True)

    file_size = source_path.stat().st_size
    total_chunks = max(1, math.ceil(file_size / args.chunk_size))
    sha256_text = file_sha256(source_path)

    meta_payload = encode_envelope(
        'meta',
        transfer_id=transfer_id,
        file_name=source_path.name,
        file_size=file_size,
        chunk_size=args.chunk_size,
        total_chunks=total_chunks,
        file_sha256=sha256_text,
    )
    print(f'start transfer_id={transfer_id} file={source_path.name} size={file_size} total_chunks={total_chunks}', flush=True)
    send_with_retry(
        client=client,
        inbox=inbox,
        dest_ip=args.dest_ip,
        payload=meta_payload,
        transfer_id=transfer_id,
        ack_for='meta',
        ack_timeout_sec=args.ack_timeout_sec,
        poll_interval_sec=args.poll_interval_sec,
        max_retries=args.max_retries,
    )

    with source_path.open('rb') as handle:
        for chunk_id in range(total_chunks):
            raw_chunk = handle.read(args.chunk_size)
            if chunk_id != total_chunks - 1 and not raw_chunk:
                raise RuntimeError(f'unexpected EOF at chunk {chunk_id}')
            chunk_payload = encode_envelope(
                'chunk',
                transfer_id=transfer_id,
                file_name=source_path.name,
                chunk_id=chunk_id,
                total_chunks=total_chunks,
                payload_b64=b64encode_bytes(raw_chunk),
                chunk_size=len(raw_chunk),
                chunk_sha256=bytes_sha256(raw_chunk),
            )
            send_with_retry(
                client=client,
                inbox=inbox,
                dest_ip=args.dest_ip,
                payload=chunk_payload,
                transfer_id=transfer_id,
                ack_for='chunk',
                ack_timeout_sec=args.ack_timeout_sec,
                poll_interval_sec=args.poll_interval_sec,
                max_retries=args.max_retries,
                chunk_id=chunk_id,
            )
            print(f'chunk {chunk_id + 1}/{total_chunks} delivered', flush=True)

    eof_payload = encode_envelope(
        'eof',
        transfer_id=transfer_id,
        file_name=source_path.name,
        total_chunks=total_chunks,
        file_size=file_size,
        file_sha256=sha256_text,
    )
    ack = send_with_retry(
        client=client,
        inbox=inbox,
        dest_ip=args.dest_ip,
        payload=eof_payload,
        transfer_id=transfer_id,
        ack_for='eof',
        ack_timeout_sec=args.ack_timeout_sec,
        poll_interval_sec=args.poll_interval_sec,
        max_retries=args.max_retries,
    )
    print(f'transfer complete: {ack}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

