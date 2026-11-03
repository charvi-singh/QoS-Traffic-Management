#!/usr/bin/env python3
"""Mininet topology + OVS QoS queues + D1 demo for the QoS Traffic Management project.

            h1 (class A sender) --\\
            h2 (class B sender) ---+-- s1 ==[ bottleneck 5 Mbit/s ]== s2 -- h4 (receiver)
            h3 (class C sender) --/        (s1-eth4, HTB queues 1/2/3)

The bottleneck is enforced by an OVS linux-htb QoS on s1-eth4 (root max-rate
5 Mbit/s) with three priority queues: 1 = class A, 2 = class B, 3 = class C.
Which queue a packet uses is decided by the Ryu controller (set_queue action),
so with QOS_MODE=baseline everything shares the default queue.

Usage (controller must already be running on 127.0.0.1:6653):
    sudo python3 topology/qos_topo.py --cli               # topology + CLI
    sudo python3 topology/qos_topo.py --demo --label qos   # run D1 demo
"""
import argparse
import json
import os
import subprocess
import sys
import time

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
BOTTLENECK_IF = "s1-eth4"
BOTTLENECK_BPS = 5_000_000


class QosTopo(Topo):
    def build(self):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")
        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")
        h3 = self.addHost("h3", ip="10.0.0.3/24")
        h4 = self.addHost("h4", ip="10.0.0.4/24")
        # explicit port numbers: the controller relies on s1 port 4 = bottleneck
        self.addLink(h1, s1, port2=1)
        self.addLink(h2, s1, port2=2)
        self.addLink(h3, s1, port2=3)
        self.addLink(s1, s2, port1=4, port2=1)
        self.addLink(h4, s2, port2=2)


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def clear_qos():
    sh("ovs-vsctl --all destroy qos")
    sh("ovs-vsctl --all destroy queue")


def configure_qos():
    """Create HTB QoS on the bottleneck port: queue1=A (prio 1), 2=B, 3=C."""
    clear_qos()
    cmd = (
        f"ovs-vsctl -- set port {BOTTLENECK_IF} qos=@newqos "
        f"-- --id=@newqos create qos type=linux-htb other-config:max-rate={BOTTLENECK_BPS} "
        "queues:1=@q1 queues:2=@q2 queues:3=@q3 "
        f"-- --id=@q1 create queue other-config:min-rate=1000000 other-config:max-rate={BOTTLENECK_BPS} other-config:priority=1 "
        f"-- --id=@q2 create queue other-config:min-rate=2000000 other-config:max-rate={BOTTLENECK_BPS} other-config:priority=2 "
        f"-- --id=@q3 create queue other-config:min-rate=1000000 other-config:max-rate={BOTTLENECK_BPS} other-config:priority=3"
    )
    r = sh(cmd)
    if r.returncode != 0:
        info(f"*** QoS config failed: {r.stderr}\n")
    else:
        info("*** OVS HTB QoS configured on %s (5 Mbit/s, queues 1/2/3)\n" % BOTTLENECK_IF)


# offered load per class (kbit/s, packet bytes, burst) - total 8.4 Mbit/s > 5 Mbit/s bottleneck
LOAD = {
    "h1": dict(cid=0, rate=400, size=200, burst=1),     # A voice-like
    "h2": dict(cid=1, rate=2000, size=1000, burst=4),   # B video-like, bursty
    "h3": dict(cid=2, rate=6000, size=1400, burst=1),   # C bulk, saturates the link
}


def run_demo(net, label, duration):
    outdir = os.path.join(ROOT, "results")
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, f"d1_{label}.csv")
    json_path = os.path.join(outdir, f"d1_{label}_summary.json")
    h4 = net.get("h4")

    info(f"*** Starting receiver on h4, then 3 senders for {duration}s (label={label})\n")
    rx = h4.popen(["python3", os.path.join(APP, "udp_receiver.py"), "--duration", str(duration + 8),
                   "--csv", csv_path, "--json", json_path], stdout=subprocess.PIPE, text=True)
    time.sleep(1)
    senders = []
    for hname, p in LOAD.items():
        h = net.get(hname)
        senders.append(h.popen(
            ["python3", os.path.join(APP, "udp_sender.py"), "--dst", h4.IP(), "--class-id", str(p["cid"]),
             "--rate-kbps", str(p["rate"]), "--size", str(p["size"]), "--burst", str(p["burst"]),
             "--duration", str(duration)], stdout=subprocess.PIPE, text=True))
    for s in senders:
        print(s.communicate()[0].strip())
    out = rx.communicate()[0]
    print(out)

    flows = sh("ovs-ofctl -O OpenFlow13 dump-flows s1").stdout
    qos = sh("ovs-appctl qos/show " + BOTTLENECK_IF).stdout
    with open(os.path.join(outdir, f"d1_{label}_flows.txt"), "w") as f:
        f.write("=== s1 flow table ===\n" + flows + "\n=== queue/QoS config ===\n" + qos + "\n")
        f.write("\n=== receiver output ===\n" + out)
    print("=== s1 flow table (class rules with set_queue in qos mode) ===")
    print(flows)
    return json_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="run the D1 traffic demo and exit")
    ap.add_argument("--cli", action="store_true", help="drop into Mininet CLI")
    ap.add_argument("--label", default="run", help="name used for result files (baseline|qos)")
    ap.add_argument("--duration", type=int, default=10)
    ap.add_argument("--controller-ip", default="127.0.0.1")
    ap.add_argument("--controller-port", type=int, default=6653)
    args = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit("Run with sudo")
    setLogLevel("info")
    net = Mininet(topo=QosTopo(), switch=OVSSwitch, controller=None, autoSetMacs=True)
    net.addController("c0", controller=RemoteController, ip=args.controller_ip, port=args.controller_port)
    net.start()
    try:
        net.waitConnected(timeout=15)
        configure_qos()
        net.staticArp()
        info("*** Connectivity check\n")
        loss = net.pingAll()
        if args.demo:
            run_demo(net, args.label, args.duration)
            with open(os.path.join(ROOT, "results", f"d1_{args.label}_ping.json"), "w") as f:
                json.dump({"pingall_loss_pct": loss}, f)
        if args.cli or not args.demo:
            CLI(net)
    finally:
        net.stop()
        clear_qos()


if __name__ == "__main__":
    main()
