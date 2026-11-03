#!/usr/bin/env python3
"""UDP receiver for all traffic classes.

Listens on the class ports (5001/5002/5003), logs every packet to a CSV and
prints per-class throughput, loss, latency and jitter at the end.

Example:
    python3 udp_receiver.py --duration 15 --csv results/run1.csv
Stops after --duration seconds, or earlier once every class has sent FIN and
no data has arrived for --idle seconds.
"""
import argparse
import csv
import json
import os
import select
import socket
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qos_common import CLASSES, TYPE_DATA, TYPE_FIN, unpack  # noqa: E402


def percentile(vals, p):
    if not vals:
        return 0.0
    vals = sorted(vals)
    k = min(len(vals) - 1, int(round(p / 100.0 * (len(vals) - 1))))
    return vals[k]


def main():
    ap = argparse.ArgumentParser(description="UDP QoS receiver")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--duration", type=float, default=20.0, help="max run time (s)")
    ap.add_argument("--idle", type=float, default=1.5, help="stop this long after all FINs seen")
    ap.add_argument("--csv", default=None, help="per-packet CSV log")
    ap.add_argument("--json", default=None, help="write summary JSON here")
    ap.add_argument("--ports", default=None, help="comma list of ports (default: all class ports)")
    args = ap.parse_args()

    ports = [int(p) for p in args.ports.split(",")] if args.ports else [c["port"] for c in CLASSES.values()]
    socks = {}
    for p in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        s.bind((args.bind, p))
        s.setblocking(False)
        socks[s] = p
    print(f"[receiver] listening on {ports}", flush=True)

    stats = {cid: {"rx": 0, "bytes": 0, "lat": [], "first": None, "last": None,
                   "max_seq": -1, "seen": set(), "dups": 0, "fin_total": None}
             for cid in CLASSES}
    writer = None
    fh = None
    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
        fh = open(args.csv, "w", newline="")
        writer = csv.writer(fh)
        writer.writerow(["class", "seq", "send_ts", "recv_ts", "latency_ms", "bytes"])

    t0 = time.time()
    all_fin_at = None
    while time.time() - t0 < args.duration:
        r, _, _ = select.select(list(socks), [], [], 0.2)
        now = time.time()
        for s in r:
            while True:
                try:
                    data, _ = s.recvfrom(65535)
                except BlockingIOError:
                    break
                try:
                    ptype, cid, seq, ts, _pad = unpack(data)
                except ValueError:
                    continue
                if cid not in stats:
                    continue
                st = stats[cid]
                if ptype == TYPE_FIN:
                    st["fin_total"] = seq
                    continue
                if seq in st["seen"]:
                    st["dups"] += 1
                    continue
                st["seen"].add(seq)
                st["rx"] += 1
                st["bytes"] += len(data)
                lat = (now - ts) * 1000.0
                st["lat"].append(lat)
                st["max_seq"] = max(st["max_seq"], seq)
                st["first"] = now if st["first"] is None else st["first"]
                st["last"] = now
                if writer:
                    writer.writerow([cid, seq, f"{ts:.6f}", f"{now:.6f}", f"{lat:.3f}", len(data)])
        active = [c for c, s in stats.items() if s["rx"] > 0]
        if active and all(stats[c]["fin_total"] is not None for c in active):
            all_fin_at = all_fin_at or now
            if now - all_fin_at > args.idle:
                break

    if fh:
        fh.close()

    summary = {}
    print("\nClass | rx pkts | expected | loss %  | thr kbps | lat avg/p95/max ms | jitter ms")
    print("------+---------+----------+---------+----------+--------------------+----------")
    for cid, st in stats.items():
        if st["rx"] == 0 and st["fin_total"] is None:
            continue
        expected = st["fin_total"] if st["fin_total"] is not None else st["max_seq"] + 1
        loss = 100.0 * (expected - st["rx"]) / expected if expected else 0.0
        span = (st["last"] - st["first"]) if st["rx"] > 1 else 0
        thr = st["bytes"] * 8 / 1000.0 / span if span > 0 else 0.0
        lat = st["lat"]
        avg = statistics.mean(lat) if lat else 0.0
        jit = statistics.pstdev(lat) if len(lat) > 1 else 0.0
        summary[CLASSES[cid]["name"]] = {
            "rx": st["rx"], "expected": expected, "loss_pct": round(loss, 2),
            "throughput_kbps": round(thr, 1), "lat_avg_ms": round(avg, 2),
            "lat_p95_ms": round(percentile(lat, 95), 2), "lat_max_ms": round(max(lat) if lat else 0, 2),
            "jitter_ms": round(jit, 2), "duplicates": st["dups"],
        }
        print(f"  {CLASSES[cid]['name']}   | {st['rx']:7d} | {expected:8d} | {loss:6.2f}  | {thr:8.1f} | "
              f"{avg:7.1f}/{percentile(lat,95):6.1f}/{(max(lat) if lat else 0):6.1f} | {jit:7.2f}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
