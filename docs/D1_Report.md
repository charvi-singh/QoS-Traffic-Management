# QoS Traffic Management System (SDN + UDP Sockets)

**Computer Networks (UE25CS243A) — SDN-Socket Programming Jackfruit Mini Project, Project 5**

## 1. Project Overview

This project implements a Software-Defined Networking (SDN)-based Quality of Service (QoS) Traffic Management System using Python UDP sockets, the Ryu SDN controller, OpenFlow 1.3, Mininet and Open vSwitch (OVS).

The application generates three simulated UDP traffic classes:

- **Class A:** Voice-like traffic
- **Class B:** Video-like traffic
- **Class C:** Bulk / best-effort traffic

The Ryu controller identifies traffic using UDP destination ports and installs OpenFlow rules that assign packets to corresponding OVS HTB queues.

The objective is to demonstrate traffic classification, queue assignment and differentiated traffic handling.

## 2. Traffic Classification

| Class | Traffic type | UDP port | OVS queue |
|---|---|---:|---:|
| A | Voice-like | 5001 | 1 |
| B | Video-like | 5002 | 2 |
| C | Bulk / best effort | 5003 | 3 |

## 3. Technologies Used

| Technology | Purpose |
|---|---|
| Python | UDP sender, receiver and controller implementation |
| UDP sockets | Traffic generation and reception |
| Ryu 4.34 | SDN controller |
| OpenFlow 1.3 | Controller-to-switch communication |
| Mininet 2.3.0 | Virtual network emulation |
| Open vSwitch 2.17.12 | Software switching and queue management |
| Linux HTB | Bandwidth-based queue configuration |

## 4. Network Topology

The implemented Mininet topology consists of:

- Three hosts: h1, h2 and h3
- One Open vSwitch: s1
- One Ryu controller connected using OpenFlow 1.3

Host IP addresses:

| Host | IP address |
|---|---|
| h1 | 10.0.0.1/24 |
| h2 | 10.0.0.2/24 |
| h3 | 10.0.0.3/24 |

## 5. Repository Structure

```text
app/
    qos_common.py
    udp_sender.py
    udp_receiver.py

controller/
    ryu_qos_controller.py

topology/
    topology.py

```

The application contains the UDP packet format, traffic generator and receiver. The controller performs traffic classification and queue selection. The topology file creates the Mininet network.

## 6. How the System Works

1. The UDP sender generates packets with a class ID, sequence number and sending timestamp.
2. Packets enter the Open vSwitch.
3. The Ryu controller installs OpenFlow rules to classify UDP traffic based on destination ports.
4. The controller maps UDP ports 5001, 5002 and 5003 to queues 1, 2 and 3.
5. OVS uses the configured HTB queues to manage traffic on its egress interfaces.
6. The receiver calculates packet loss, throughput, latency and jitter.

## 7. QoS Queue Configuration

The implementation uses OVS QoS with the Linux HTB queueing discipline.

The configured queue parameters reported during testing are:

| Queue | Traffic class | Minimum rate | Maximum rate |
|---|---|---:|---:|
| 1 | Class A | 1 Mbps | 10 Mbps |
| 2 | Class B | 1 Mbps | 5 Mbps |
| 3 | Class C | 500 Kbps | 500 Kbps |

The parent QoS maximum rate is reported as 10 Mbps.

## 8. Testing and Evaluation

The project includes the following tests:

- Mininet host connectivity using `pingall`.
- Ryu controller and OVS connectivity.
- OpenFlow flow-table verification.
- OVS QoS and queue configuration verification.
- Individual UDP traffic tests for Classes A, B and C.
- Simultaneous traffic generation and receiver-side measurement.

The receiver measures:

| Metric | Description |
|---|---|
| Throughput | Successfully received data per unit time |
| Packet loss | Percentage of expected packets not received |
| Latency | Time taken for a packet to reach the receiver |
| Jitter | Variation in packet delay |

Individual tests recorded successful packet reception for all three classes. In the simultaneous test, Classes A and B were recorded at the receiver, while Class C was not recorded. Further testing is required to establish complete three-class QoS performance under simultaneous congestion.

## 9. D1 and D2 Scope

**D1 — Initial implementation**

- UDP sender and receiver.
- Mininet topology.
- Ryu controller integration.
- OpenFlow traffic classification.
- OVS HTB queue configuration.
- Initial traffic testing and measurement.

**D2 — Planned extensions**

- Dynamic congestion detection using switch port statistics.
- Runtime QoS policy changes.
- Link-failure and robustness testing.
- Jain's fairness index.
- Multiple traffic-load experiments.
- Performance graphs and comparative evaluation.

## 10. Project Outcome

The D1 implementation demonstrates the integration of UDP socket programming with an SDN controller and OVS queue-based traffic management. It verifies destination-port-based traffic classification and queue assignment, along with individual traffic reception tests.

Further simultaneous congestion testing is required to quantify the QoS performance improvement across all three traffic classes.
