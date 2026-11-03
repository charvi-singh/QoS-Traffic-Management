# QoS Traffic Management System (SDN + UDP sockets)

Computer Networks (UE25CS243A) – SDN-Socket Programming Jackfruit Mini Project, **Project 5**.

A UDP application generates three traffic classes. During congestion on a 5 Mbit/s bottleneck link, an
SDN (Ryu / OpenFlow 1.3) controller classifies the flows and steers them into prioritised Open vSwitch
queues so that latency-sensitive traffic is protected.

| Class | Meaning | UDP port | Packet | Offered load |
|---|---|---|---|---|
| A | voice-like, small + steady, highest priority | 5001 | 200 B | 0.4 Mbit/s |
| B | video-like, medium + bursty | 5002 | 1000 B (bursts of 4) | 2 Mbit/s |
| C | bulk / best effort | 5003 | 1400 B | 6 Mbit/s |

Total offered load 8.4 Mbit/s vs. 5 Mbit/s bottleneck = controlled congestion.

## Repository layout
```
app/qos_common.py      packet format + class definitions
app/udp_sender.py      per-class UDP traffic generator (rate, size, burst, duration)
app/udp_receiver.py    receiver; logs per-packet CSV; prints loss / throughput / latency / jitter
topology/qos_topo.py   Mininet topology + OVS HTB queues on the bottleneck + D1 demo runner
controller/qos_ryu.py  Ryu controller: learning switch + UDP port classification + set_queue
scripts/run_d1.sh      runs the demo in baseline and qos mode, then compares
scripts/compare.py     baseline vs QoS table
results/               CSV logs, JSON summaries, flow-table dumps, controller logs
docs/D1_Report.md      D1 report
```

## Topology
```
h1 (A) --\
h2 (B) ---+-- s1 ==== 5 Mbit/s bottleneck (s1-eth4, HTB queues 1/2/3) ==== s2 -- h4 (receiver)
h3 (C) --/
```
Controller: remote, `127.0.0.1:6653`. IPs: h1..h4 = 10.0.0.1 .. 10.0.0.4.

## Setup (Ubuntu VM)
```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch python3-pip git iperf3 tshark
sudo mn --test pingall          # sanity check: 0% dropped
```
**Ryu** does not install on new Python versions (3.10+). Use a Python 3.9 virtualenv (tested recipe):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.local/bin/env
uv venv --python 3.9 ~/ryu-env
~/ryu-env/bin/python -m ensurepip
~/ryu-env/bin/python -m pip install "setuptools<58" wheel eventlet==0.30.2
~/ryu-env/bin/python -m pip install --no-build-isolation ryu
~/ryu-env/bin/ryu-manager --version
```

## Run the D1 demo (automatic)
```bash
git clone <your-repo-url> && cd qos-sdn
./scripts/run_d1.sh            # baseline run, then QoS run, then comparison table
```

## Run manually (3 terminals)
```bash
# terminal 1 – controller (mode: qos | baseline)
QOS_MODE=qos ~/ryu-env/bin/ryu-manager controller/qos_ryu.py
# terminal 2 – topology + Mininet CLI
sudo python3 topology/qos_topo.py --cli
# in the mininet> CLI
mininet> h4 python3 app/udp_receiver.py --duration 20 --csv results/manual.csv &
mininet> h1 python3 app/udp_sender.py --dst 10.0.0.4 --class-id 0 --rate-kbps 400  --size 200  --duration 10 &
mininet> h2 python3 app/udp_sender.py --dst 10.0.0.4 --class-id 1 --rate-kbps 2000 --size 1000 --burst 4 --duration 10 &
mininet> h3 python3 app/udp_sender.py --dst 10.0.0.4 --class-id 2 --rate-kbps 6000 --size 1400 --duration 10
# terminal 3 – inspect the SDN state
sudo ovs-ofctl -O OpenFlow13 dump-flows s1      # class rules (look for set_queue)
sudo ovs-appctl qos/show s1-eth4                # queue config / counters
```
Cleanup if Mininet misbehaves: `sudo mn -c`

## How it works
1. `udp_sender.py` stamps each packet with class id, sequence number and send time.
2. Packets reach s1; the first packet of a flow goes to the controller (packet-in).
3. `qos_ryu.py` classifies by UDP destination port and installs a priority-200 flow rule. In `qos` mode the
   rule includes `set_queue(1|2|3)` for the bottleneck port; in `baseline` mode it does not.
4. The OVS HTB queues (priority 1 = A, 2 = B, 3 = C) serve class A first when the link is congested.
5. `udp_receiver.py` computes loss (sequence gaps / FIN total), throughput, latency and jitter per class.

## Status
* D1: sockets, topology, controller classification + queue mapping, end-to-end demo, baseline-vs-QoS first look.
* D2 (planned): congestion detection through port-stats polling and *dynamic* policy changes at runtime,
  link-failure / robustness scenario, Jain fairness index, multiple load levels, graphs, final report.
