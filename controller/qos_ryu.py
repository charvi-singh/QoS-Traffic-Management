"""Ryu (OpenFlow 1.3) controller for the QoS Traffic Management System - D1.

Behaviour
---------
* Acts as an L2 learning switch for all traffic (ARP, ICMP, ...).
* Classifies UDP traffic by destination port into traffic classes
  (5001 = A voice-like, 5002 = B video-like, 5003 = C bulk) and installs a
  dedicated, higher-priority flow rule per (src, dst, class).
* QOS_MODE=qos      -> rule actions include set_queue(<class queue>) when the
                       packet leaves via the bottleneck port of s1. The OVS
                       queues (HTB with priorities) are created by
                       topology/qos_topo.py, so class A is served first.
* QOS_MODE=baseline -> same rules but NO set_queue: every class shares the
                       default queue (best-effort FIFO). Used as comparison.

Run:   QOS_MODE=qos ryu-manager controller/qos_ryu.py
"""
import os

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib.packet import ethernet, ether_types, ipv4, packet, udp
from ryu.ofproto import ofproto_v1_3

# class UDP dst port -> (class name, OVS queue id on the bottleneck port)
CLASS_BY_PORT = {5001: ("A", 1), 5002: ("B", 2), 5003: ("C", 3)}
INGRESS_DPID = 1        # s1: the switch whose uplink is the bottleneck
BOTTLENECK_PORT = 4     # s1-eth4 -> s2 (set in qos_topo.py)


class QosController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.mode = os.environ.get("QOS_MODE", "qos").lower()
        self.logger.info("QoS controller started, mode=%s", self.mode)

    # ---- switch handshake: install table-miss -----------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._add_flow(dp, 0, match, actions)
        self.logger.info("s%s connected, table-miss installed", dp.id)

    def _add_flow(self, dp, priority, match, actions, idle=60):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                      instructions=inst, idle_timeout=idle))

    # ---- packet-in: learn, classify, install ------------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(dp.id, {})[eth.src] = in_port
        out_port = self.mac_to_port[dp.id].get(eth.dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofp.OFPP_FLOOD:
            ip = pkt.get_protocol(ipv4.ipv4)
            u = pkt.get_protocol(udp.udp)
            if ip and u and u.dst_port in CLASS_BY_PORT:
                cname, queue = CLASS_BY_PORT[u.dst_port]
                match = parser.OFPMatch(eth_type=0x0800, ipv4_src=ip.src, ipv4_dst=ip.dst,
                                        ip_proto=17, udp_dst=u.dst_port)
                acts = []
                use_queue = (self.mode == "qos" and dp.id == INGRESS_DPID
                             and out_port == BOTTLENECK_PORT)
                if use_queue:
                    acts.append(parser.OFPActionSetQueue(queue))
                acts.append(parser.OFPActionOutput(out_port))
                self._add_flow(dp, 200, match, acts)
                self.logger.info("s%s: class %s %s->%s udp/%d -> port %s%s", dp.id, cname,
                                 ip.src, ip.dst, u.dst_port, out_port,
                                 f" queue {queue}" if use_queue else " (default queue)")
            else:
                match = parser.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src)
                self._add_flow(dp, 10, match, actions)

        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                        in_port=in_port, actions=actions, data=data))
