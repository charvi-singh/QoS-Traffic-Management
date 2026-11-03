"""Shared definitions for the QoS UDP application.

Packet layout (network byte order), 18-byte header followed by padding:

    type      : 1 byte   0 = DATA, 1 = FIN (end of stream marker)
    class_id  : 1 byte   0 = A (voice-like), 1 = B (video-like), 2 = C (bulk)
    seq       : 4 bytes  DATA: sequence number, FIN: total packets sent
    send_ts   : 8 bytes  sender wall-clock time (double, seconds)
    payload_len: 4 bytes length of padding that follows (sanity check)
"""
import struct

HEADER_FMT = "!BBIdI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 18 bytes

TYPE_DATA = 0
TYPE_FIN = 1

# Traffic classes. The UDP destination port identifies the class; the SDN
# controller classifies flows by this port and maps them to an OVS queue.
CLASSES = {
    0: {"name": "A", "desc": "voice-like (small, steady, high priority)", "port": 5001, "queue": 1},
    1: {"name": "B", "desc": "video-like (medium, bursty)",               "port": 5002, "queue": 2},
    2: {"name": "C", "desc": "bulk / best effort (large, fast)",          "port": 5003, "queue": 3},
}
PORT_TO_CLASS = {v["port"]: k for k, v in CLASSES.items()}


def pack(ptype, class_id, seq, send_ts, total_size):
    pad = max(0, total_size - HEADER_SIZE)
    return struct.pack(HEADER_FMT, ptype, class_id, seq, send_ts, pad) + b"\x00" * pad


def unpack(data):
    if len(data) < HEADER_SIZE:
        raise ValueError("short packet")
    ptype, class_id, seq, ts, pad = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    return ptype, class_id, seq, ts, pad
