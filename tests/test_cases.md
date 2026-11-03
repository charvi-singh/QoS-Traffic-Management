# QoS Traffic Management - D1 Testing Checklist

## 1. Environment Testing
- [x] Python installed
- [x] Mininet installed
- [x] Open vSwitch installed
- [x] Basic Mininet connectivity verified

## 2. UDP Application Testing
- [ ] UDP receiver starts successfully
- [ ] Voice traffic received (Port 5001)
- [ ] Video traffic received (Port 5002)
- [ ] Bulk traffic received (Port 5003)

## 3. SDN Controller Testing
- [ ] Ryu controller starts
- [ ] Mininet connects to Ryu
- [ ] Flow rules installed
- [ ] Traffic classes identified correctly

## 4. QoS Testing
- [ ] QoS queues configured
- [ ] Voice traffic gets high priority
- [ ] Video traffic gets medium priority
- [ ] Bulk traffic gets low priority

## 5. Performance Testing
- [ ] Baseline experiment completed
- [ ] QoS experiment completed
- [ ] Throughput recorded
- [ ] Latency recorded
- [ ] Packet loss recorded
- [ ] Baseline and QoS compared

## 6. Submission
- [x] GitHub repository created
- [x] Project uploaded
- [ ] Team members invited
- [ ] Screenshots collected
- [ ] D1 report finalized
