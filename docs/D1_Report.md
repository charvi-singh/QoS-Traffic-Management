---
title: "QoS Traffic Management System – D1 Report"
subtitle: "SDN-Socket Programming Jackfruit Mini Project (UE25CS243A) – Project 5"
---

**Team members:** _<Name 1 – SRN>_, _<Name 2 – SRN>_, _<Name 3 – SRN>_
**GitHub repository:** _<link>_
**Protocol:** UDP  |  **Controller:** Ryu (OpenFlow 1.3)  |  **Emulator:** Mininet + Open vSwitch

# 1. Problem Understanding & Architecture

**Problem.** When many applications share a congested link, a FIFO queue treats all packets alike, so delay-sensitive
traffic (voice) suffers the same loss and queueing delay as bulk transfers. The project builds a UDP application that
generates different traffic classes and uses an SDN controller to prioritise selected flows during congestion.

**Objectives.**

1. Generate multiple UDP traffic classes (A voice-like, B video-like, C bulk).
2. Classify application flows in the SDN controller.
3. Implement SDN-based priority policies (OpenFlow rules mapping classes to OVS priority queues).
4. Create controlled congestion and measure throughput, latency and packet loss per class.
5. Compare with a no-QoS baseline and analyse fairness; (D2) modify policies dynamically at run time.

**Architecture.**

```
h1 (A) --\
h2 (B) ---+-- s1 ==== 5 Mbit/s bottleneck (s1-eth4, HTB queues 1/2/3) ==== s2 -- h4 (receiver)
h3 (C) --/                       |
                         Ryu controller (OpenFlow 1.3, 127.0.0.1:6653)
```

| Component | Role |
|---|---|
| `udp_sender.py` (h1,h2,h3) | Generates one class each: rate, packet size, burst, duration configurable |
| `udp_receiver.py` (h4) | Receives on ports 5001-5003, logs every packet, computes loss/throughput/latency/jitter |
| Mininet topology | 4 hosts, 2 OVS switches, bottleneck link s1-s2 |
| OVS HTB QoS on `s1-eth4` | Root rate 5 Mbit/s; queue 1 (A, priority 1), queue 2 (B, priority 2), queue 3 (C, priority 3) |
| Ryu controller | Learning switch + classification by UDP destination port + `set_queue` flow rules |

**Communication flow.** Sender → s1 → (table miss → packet-in to controller) → controller installs a class rule
`match(ipv4_src, ipv4_dst, udp_dst) → set_queue(q), output(4)` → subsequent packets are forwarded in the switch at line
rate through the class queue → s2 → receiver.

**Application protocol (18-byte header).**

| Field | Size | Meaning |
|---|---|---|
| type | 1 B | 0 = DATA, 1 = FIN (carries total packets sent, used for exact loss computation) |
| class_id | 1 B | 0 = A, 1 = B, 2 = C |
| seq | 4 B | sequence number |
| send_ts | 8 B | sender timestamp (all hosts share the VM clock, so one-way latency is valid) |
| payload_len | 4 B | padding length |

**Traffic classes.**

| Class | UDP port | OVS queue | Packet size | Offered load | Nature |
|---|---|---|---|---|---|
| A | 5001 | 1 (highest) | 200 B | 0.4 Mbit/s | small, steady |
| B | 5002 | 2 | 1000 B | 2 Mbit/s | bursty (4 back-to-back) |
| C | 5003 | 3 | 1400 B | 6 Mbit/s | bulk, saturating |

Total offered load is 8.4 Mbit/s against a 5 Mbit/s bottleneck, which creates sustained congestion.

# 2. TCP/UDP Socket Implementation

* Low-level `socket.SOCK_DGRAM` sockets only; no application framework.
* **Sender:** time-paced loop (target rate computed from packet size), optional bursts to model bursty video, FIN marker
  sent five times because a single FIN could be dropped under congestion.
* **Receiver:** one non-blocking UDP socket per class port multiplexed with `select`; enlarged receive buffer
  (4 MB); duplicate detection through a sequence set; invalid or short packets ignored; runs until all FINs are seen
  or a timeout expires.
* **Concurrency:** three sender processes run in parallel on h1-h3 while one receiver serves all classes.
* **Metrics:** per-class received packets, loss % (FIN total vs. received), throughput (kbit/s), latency
  (avg / p95 / max) and jitter (standard deviation of latency); a per-packet CSV is stored in `results/`.

# 3. Mininet + SDN Implementation

* **Topology** (`topology/qos_topo.py`): 4 hosts, 2 OpenFlow 1.3 switches, explicit port numbers so the controller
  knows that `s1` port 4 is the bottleneck; remote controller on 127.0.0.1:6653; static ARP removes broadcast noise.
* **Bottleneck:** an Open vSwitch `linux-htb` QoS on `s1-eth4` limits the link to 5 Mbit/s and defines three queues
  with guaranteed minimum rates (1 / 2 / 1 Mbit/s) and strict priorities (1 > 2 > 3).
* **Controller** (`controller/qos_ryu.py`):
  * learning-switch behaviour for ARP/ICMP and unclassified traffic (priority 10),
  * UDP classification by destination port into classes A/B/C (priority 200 rules),
  * `QOS_MODE=qos` adds `set_queue` to the bottleneck-bound rule, `QOS_MODE=baseline` omits it, giving a
    static no-QoS reference for the comparison required by the rubric.

# 4. Socket–SDN Integration

The socket application's traffic drives the controller: the first datagram of each class flow raises a packet-in,
the controller identifies the class from the UDP port carried by the application, and installs a rule that places
the flow in the matching priority queue. The application's class definition (port ↔ class) is shared between
`qos_common.py` and the controller, so application events directly determine SDN behaviour. The installed rules
are visible with `ovs-ofctl dump-flows s1` (`set_queue:N` actions) and are saved to `results/d1_<mode>_flows.txt`.

# 5. Initial Testing & Demo

| # | Test | How | Expected |
|---|---|---|---|
| T1 | Topology connectivity | `pingall` in Mininet | 0 % loss, 4 hosts reachable |
| T2 | Controller connection | controller log | s1 and s2 connected, table-miss installed |
| T3 | UDP app, no congestion | one class alone | 0 % loss, throughput ≈ offered load |
| T4 | Classification | `dump-flows s1` after traffic | three priority-200 rules, one per class, with `set_queue:1/2/3` (qos mode) |
| T5 | Congestion, baseline | `QOS_MODE=baseline`, all three classes | all classes show loss; class A latency high |
| T6 | Congestion, SDN QoS | `QOS_MODE=qos`, all three classes | class A loss ≈ 0 and low latency; class C absorbs the loss |

**Reproduce:** `./scripts/run_d1.sh` (see README).

## Results (fill in from your own run – `results/d1_*_summary.json`, `python3 scripts/compare.py`)

| Class | Metric | Baseline (no QoS) | SDN QoS |
|---|---|---|---|
| A | loss % | _..._ | _..._ |
| A | avg latency (ms) | _..._ | _..._ |
| B | loss % | _..._ | _..._ |
| B | throughput (kbit/s) | _..._ | _..._ |
| C | loss % | _..._ | _..._ |
| C | throughput (kbit/s) | _..._ | _..._ |

_Screenshots to add:_ topology/`net` output, `pingall`, controller log with class rules, `dump-flows s1`, receiver
summary for both modes.

# 6. Planned work for D2

1. **Dynamic SDN functionality:** poll port statistics (OFPPortStatsRequest) on the bottleneck, detect congestion
   from utilisation, and switch the policy at run time (enable priority queues, tighten or relax class limits,
   optionally OpenFlow meters) without restarting the network.
2. **Challenging scenario:** link failure / heavier overload, with the controller reacting.
3. **Performance evaluation:** several load levels, baseline vs. static priority vs. dynamic priority,
   Jain's fairness index between classes, graphs for throughput, latency and loss.
4. **Documentation, final demo and viva preparation.**
