#!/usr/bin/env bash
# Runs the D1 demo twice (baseline = no QoS, qos = SDN priority queues) and prints both results.
# Usage:  ./scripts/run_d1.sh            (needs: mininet, openvswitch, ryu in ~/ryu-env)
set -u
cd "$(dirname "$0")/.."
RYU="${RYU:-$HOME/ryu-env/bin/ryu-manager}"
DUR="${DUR:-10}"

for MODE in baseline qos; do
  echo "================ MODE: $MODE ================"
  sudo mn -c >/dev/null 2>&1
  QOS_MODE=$MODE "$RYU" controller/qos_ryu.py > "results/controller_$MODE.log" 2>&1 &
  RYU_PID=$!
  sleep 4
  sudo python3 topology/qos_topo.py --demo --label "$MODE" --duration "$DUR"
  kill $RYU_PID 2>/dev/null
  wait $RYU_PID 2>/dev/null
  sleep 1
done
sudo mn -c >/dev/null 2>&1
echo
echo "Results in results/:  d1_baseline_summary.json  d1_qos_summary.json  *_flows.txt  controller_*.log"
python3 scripts/compare.py
