"""Adaptive QoS Traffic Management Controller - OpenFlow 1.3."""

import os
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    DEAD_DISPATCHER,
    set_ev_cls,
)
from ryu.lib import hub
from ryu.lib.packet import ethernet, ether_types, ipv4, packet, udp
from ryu.ofproto import ofproto_v1_3


CLASS_BY_PORT = {
    5001: ("A", 1),
    5002: ("B", 2),
    5003: ("C", 3),
}

INGRESS_DPID = 1
BOTTLENECK_PORT = 4

BOTTLENECK_CAPACITY_KBPS = 5000
HIGH_THRESHOLD_KBPS = 4000
LOW_THRESHOLD_KBPS = 3000

METER_ID = 1
CLASS_C_LIMIT_KBPS = 1500


class QosController(app_manager.RyuApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.mac_to_port = {}
        self.datapaths = {}

        self.mode = os.environ.get("QOS_MODE", "qos").lower()

        self.congestion_active = False
        self.high_count = 0
        self.low_count = 0

        self.last_port_sample = None

        self.logger.info(
            "Adaptive QoS controller started, mode=%s", self.mode
        )

        self.monitor_thread = hub.spawn(self._monitor)

    # ---------------------------------------------------------
    # Switch connection and table-miss rule
    # ---------------------------------------------------------

    @set_ev_cls(
        ofp_event.EventOFPStateChange,
        [MAIN_DISPATCHER, DEAD_DISPATCHER]
    )
    def state_change_handler(self, ev):
        dp = ev.datapath

        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self.logger.info("Switch s%s registered", dp.id)

        elif ev.state == DEAD_DISPATCHER:
            self.datapaths.pop(dp.id, None)
            self.logger.info("Switch s%s disconnected", dp.id)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        match = parser.OFPMatch()

        actions = [
            parser.OFPActionOutput(
                ofp.OFPP_CONTROLLER,
                ofp.OFPCML_NO_BUFFER
            )
        ]

        self._add_flow(dp, 0, match, actions, idle=0)

        self.logger.info(
            "s%s connected, table-miss installed", dp.id
        )

    # ---------------------------------------------------------
    # Flow installation
    # ---------------------------------------------------------

    def _add_flow(
        self, dp, priority, match, actions,
        idle=60, meter_id=None
    ):
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        instructions = []

        if meter_id is not None:
            instructions.append(
                parser.OFPInstructionMeter(meter_id)
            )

        instructions.append(
            parser.OFPInstructionActions(
                ofp.OFPIT_APPLY_ACTIONS,
                actions
            )
        )

        dp.send_msg(
            parser.OFPFlowMod(
                datapath=dp,
                priority=priority,
                match=match,
                instructions=instructions,
                idle_timeout=idle
            )
        )

    # ---------------------------------------------------------
    # UDP classification and forwarding
    # ---------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):

        msg = ev.msg
        dp = msg.datapath

        ofp = dp.ofproto
        parser = dp.ofproto_parser

        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)

        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(dp.id, {})
        self.mac_to_port[dp.id][eth.src] = in_port

        out_port = self.mac_to_port[dp.id].get(
            eth.dst, ofp.OFPP_FLOOD
        )

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofp.OFPP_FLOOD:

            ip = pkt.get_protocol(ipv4.ipv4)
            u = pkt.get_protocol(udp.udp)

            if ip and u and u.dst_port in CLASS_BY_PORT:

                cname, queue = CLASS_BY_PORT[u.dst_port]

                match = parser.OFPMatch(
                    eth_type=0x0800,
                    ipv4_src=ip.src,
                    ipv4_dst=ip.dst,
                    ip_proto=17,
                    udp_dst=u.dst_port
                )

                use_queue = (
                    self.mode == "qos"
                    and dp.id == INGRESS_DPID
                    and out_port == BOTTLENECK_PORT
                )

                class_actions = []

                if use_queue:
                    class_actions.append(
                        parser.OFPActionSetQueue(queue)
                    )

                class_actions.append(
                    parser.OFPActionOutput(out_port)
                )

                self._add_flow(
                    dp, 200, match, class_actions
                )

                self.logger.info(
                    "s%s: class %s %s->%s udp/%d -> port %s%s",
                    dp.id, cname, ip.src, ip.dst,
                    u.dst_port, out_port,
                    f" queue {queue}" if use_queue
                    else " (default queue)"
                )

            else:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=eth.dst,
                    eth_src=eth.src
                )

                self._add_flow(dp, 10, match, actions)

        data = (
            msg.data
            if msg.buffer_id == ofp.OFP_NO_BUFFER
            else None
        )

        dp.send_msg(
            parser.OFPPacketOut(
                datapath=dp,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data
            )
        )

    # ---------------------------------------------------------
    # Dynamic Class C meter
    # ---------------------------------------------------------

    def _set_class_c_meter(self, dp, enabled):

        ofp = dp.ofproto
        parser = dp.ofproto_parser

        if enabled:

            band = parser.OFPMeterBandDrop(
                rate=CLASS_C_LIMIT_KBPS,
                burst_size=CLASS_C_LIMIT_KBPS
            )

            meter = parser.OFPMeterMod(
                datapath=dp,
                command=ofp.OFPMC_ADD,
                flags=(
                    ofp.OFPMF_KBPS
                    | ofp.OFPMF_BURST
                    | ofp.OFPMF_STATS
                ),
                meter_id=METER_ID,
                bands=[band]
            )

            dp.send_msg(meter)

            self.logger.warning(
                "CONGESTION: applying Class C meter: %d Kbps",
                CLASS_C_LIMIT_KBPS
            )

        # This rule specifically matches Class C traffic
        # entering s1 from h3 and leaving through port 4.
        match = parser.OFPMatch(
            in_port=3,
            eth_type=0x0800,
            ip_proto=17,
            udp_dst=5003
        )

        actions = [
            parser.OFPActionSetQueue(3),
            parser.OFPActionOutput(BOTTLENECK_PORT)
        ]

        self._add_flow(
            dp,
            250,
            match,
            actions,
            idle=0,
            meter_id=METER_ID if enabled else None
        )

        if not enabled:

            meter = parser.OFPMeterMod(
                datapath=dp,
                command=ofp.OFPMC_DELETE,
                flags=0,
                meter_id=METER_ID,
                bands=[]
            )

            dp.send_msg(meter)

            self.logger.info(
                "Congestion cleared: Class C meter removed"
            )

    def _change_congestion_state(self, active):

        if self.congestion_active == active:
            return

        dp = self.datapaths.get(INGRESS_DPID)

        if dp is None:
            self.logger.warning(
                "Cannot change congestion policy: s1 disconnected"
            )
            return

        if self.mode != "qos":
            self.logger.info(
                "Congestion detected, but baseline mode is active"
            )
            return

        self._set_class_c_meter(dp, active)

        self.congestion_active = active
        self.high_count = 0
        self.low_count = 0

    # ---------------------------------------------------------
    # Port statistics monitoring
    # ---------------------------------------------------------

    def _monitor(self):

        while True:

            dp = self.datapaths.get(INGRESS_DPID)

            if dp is not None:

                parser = dp.ofproto_parser
                ofp = dp.ofproto

                request = parser.OFPPortStatsRequest(
                    dp, 0, ofp.OFPP_ANY
                )

                dp.send_msg(request)

            hub.sleep(2)

    @set_ev_cls(
        ofp_event.EventOFPPortStatsReply,
        MAIN_DISPATCHER
    )
    def port_stats_reply_handler(self, ev):

        dp = ev.msg.datapath

        if dp.id != INGRESS_DPID:
            return

        now = time.time()

        for stat in ev.msg.body:

            if stat.port_no != BOTTLENECK_PORT:
                continue

            current_bytes = stat.tx_bytes

            if self.last_port_sample is None:
                self.last_port_sample = (
                    current_bytes, now
                )
                return

            previous_bytes, previous_time = (
                self.last_port_sample
            )

            elapsed = now - previous_time

            if elapsed <= 0:
                return

            byte_delta = current_bytes - previous_bytes

            if byte_delta < 0:
                self.last_port_sample = (
                    current_bytes, now
                )
                return

            rate_kbps = (
                byte_delta * 8 / elapsed / 1000
            )

            self.last_port_sample = (
                current_bytes, now
            )

            self.logger.info(
                "Bottleneck s1 port 4 utilization: %.2f Kbps",
                rate_kbps
            )

            if rate_kbps >= HIGH_THRESHOLD_KBPS:

                self.high_count += 1
                self.low_count = 0

            elif rate_kbps <= LOW_THRESHOLD_KBPS:

                self.low_count += 1
                self.high_count = 0

            else:

                self.high_count = 0
                self.low_count = 0

            # Require two consecutive high readings.
            if (
                not self.congestion_active
                and self.high_count >= 2
            ):
                self._change_congestion_state(True)

            # Require three consecutive low readings.
            elif (
                self.congestion_active
                and self.low_count >= 3
            ):
                self._change_congestion_state(False)
