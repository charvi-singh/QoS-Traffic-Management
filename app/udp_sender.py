#!/usr/bin/env python3
"""UDP traffic generator for one traffic class.

Example (class A, 0.4 Mbps, 200-byte packets, 10 s):
    python3 udp_sender.py --dst 10.0.0.4 --class-id 0 --rate-kbps 400 --size 200 --duration 10
"""
import argparse
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qos_common import CLASSES, TYPE_DATA, TYPE_FIN, pack  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="UDP traffic class generator")
    ap.add_argument("--dst", required=True, help="receiver IP")
    ap.add_argument("--class-id", type=int, choices=sorted(CLASSES), required=True)
    ap.add_argument("--rate-kbps", type=float, required=True, help="offered load in kbit/s")
    ap.add_argument("--size", type=int, default=500, help="UDP payload bytes per packet (>= 18)")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds")
    ap.add_argument("--burst", type=int, default=1,
                    help="packets sent back-to-back per tick (>1 gives bursty traffic)")
    ap.add_argument("--port", type=int, default=None, help="override destination port")
    args = ap.parse_args()

    port = args.port or CLASSES[args.class_id]["port"]
    size = max(args.size, 18)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = (args.dst, port)

    pkts_per_sec = args.rate_kbps * 1000.0 / 8.0 / size
    interval = args.burst / pkts_per_sec  # time between ticks
    seq = 0
    start = time.time()
    next_t = start
    end = start + args.duration
    while True:
        now = time.time()
        if now >= end:
            break
        if now < next_t:
            time.sleep(min(next_t - now, 0.002))
            continue
        for _ in range(args.burst):
            sock.sendto(pack(TYPE_DATA, args.class_id, seq, time.time(), size), addr)
            seq += 1
        next_t += interval

    # FIN marker carries the total number of packets sent so the receiver can
    # compute exact loss. Sent several times because it may itself be dropped.
    for _ in range(5):
        sock.sendto(pack(TYPE_FIN, args.class_id, seq, time.time(), 18), addr)
        time.sleep(0.05)

    elapsed = time.time() - start
    print(json.dumps({
        "role": "sender", "class": CLASSES[args.class_id]["name"], "dst": args.dst,
        "port": port, "sent": seq, "size": size, "elapsed_s": round(elapsed, 3),
        "offered_kbps": round(seq * size * 8 / 1000.0 / elapsed, 1),
    }))


if __name__ == "__main__":
    main()
