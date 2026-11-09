Stage 1 – UDP Application Testing Report

Project: QoS Traffic Management System using SDN
Team Role: Member 1 – UDP Application Developer
Date: 9 November 2026
Environment: Ubuntu Linux
Protocol: UDP
1. Objective

To test the UDP sender and receiver and verify successful transmission of three traffic classes using separate UDP destination ports.
2. Traffic Classification
Class	Traffic Type	Priority	UDP Port
A	Voice-like	High	5001
B	Video-like	Medium	5002
C	Bulk/File transfer	Low	5003
3. Experimental Results
Metric	Class A	Class B	Class C
Packets received	313	250	180
Expected packets	313	250	180
Packet loss (%)	0.00	0.00	0.00
Throughput (kbps)	100.4	200.8	301.6
Average latency (ms)	0.20	0.34	0.19
P95 latency (ms)	0.43	1.03	0.71
Maximum latency (ms)	2.11	3.86	1.39
Jitter (ms)	0.19	0.49	0.22
Duplicates	0	0	0
4. Observations

    The UDP receiver successfully listened on ports 5001, 5002 and 5003.

    All three traffic classes were successfully transmitted and received.

    The receiver correctly identified each traffic class.

    All 743 expected packets were received.

    No packet loss or duplicate packets were recorded.

    Throughput, latency and jitter measurements were successfully recorded.

5. Conclusion

The UDP sender and receiver were successfully tested. All three traffic classes were correctly identified and received with 0% packet loss.

The application is ready for subsequent integration testing with Mininet, Open vSwitch and the Ryu SDN controller.

Testing limitation: These initial tests used localhost (127.0.0.1). They establish application functionality but do not establish QoS performance under network congestion.
