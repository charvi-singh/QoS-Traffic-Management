#!/usr/bin/env python3
"""Print a baseline vs QoS comparison table from results/d1_*_summary.json."""
import json
import os

R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")


def load(mode):
    p = os.path.join(R, f"d1_{mode}_summary.json")
    return json.load(open(p)) if os.path.exists(p) else {}


base, qos = load("baseline"), load("qos")
print("\nCLASS | metric            | baseline (no QoS) | SDN QoS")
print("------+-------------------+-------------------+---------")
for c in "ABC":
    for key, label in (("loss_pct", "loss %"), ("lat_avg_ms", "avg latency ms"),
                       ("lat_p95_ms", "p95 latency ms"), ("throughput_kbps", "throughput kbps")):
        b = base.get(c, {}).get(key, "-")
        q = qos.get(c, {}).get(key, "-")
        print(f"  {c}   | {label:17s} | {str(b):17s} | {q}")
