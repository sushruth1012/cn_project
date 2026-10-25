"""
controller.py - Ryu OpenFlow 1.3 SDN Controller with Real-Time Flow & Bandwidth Monitoring
------------------------------------------------------------------------------------------
Features:
- OpenFlow 1.3 Learning Switch with dynamic flow installation
- Periodic OpenFlow Statistics Polling (FlowStatsRequest, PortStatsRequest)
- Real-time calculation of byte count, packet count, and flow bandwidth (Mbps)
- Formatted console display of switch statistics
- Persistent CSV export for analysis and plotting

Usage:
  ryu-manager sdn/controller.py
  OR
  python3 sdn/controller.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
    from ryu.controller.handler import set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp, udp
    from ryu.lib import hub
except ImportError:
    # If executed in environment without Ryu installed, provide clean message
    app_manager = object
    ofp_event = None
    CONFIG_DISPATCHER = MAIN_DISPATCHER = DEAD_DISPATCHER = None
    set_ev_cls = lambda *args, **kwargs: (lambda f: f)
    ofproto_v1_3 = None

from flow_monitor import FlowStatsTracker


class BandwidthMonitoringController(app_manager.RyuApp if hasattr(app_manager, 'RyuApp') else object):
    """
    Ryu OpenFlow 1.3 controller application that routes traffic,
    installs flow entries, and monitors real-time flow and port bandwidth.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION] if ofproto_v1_3 else []

    def __init__(self, *args, **kwargs):
        super(BandwidthMonitoringController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.monitor_interval = 4  # Statistics polling interval in seconds
        self.tracker = FlowStatsTracker()
        self.monitor_thread = hub.spawn(self._monitor) if 'hub' in globals() and hasattr(hub, 'spawn') else None
        self.logger.info("=" * 60)
        self.logger.info("Bandwidth Meter SDN Controller initialized (OF 1.3)")
        self.logger.info(f"Statistics poll interval: {self.monitor_interval}s")
        self.logger.info("=" * 60)

    # ==========================================
    # Datapath Registration & Table-Miss Setup
    # ==========================================
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        """Track connected switches (datapaths)."""
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.info(f"[SDN] Switch connected: DPID=0x{datapath.id:016x}")
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.info(f"[SDN] Switch disconnected: DPID=0x{datapath.id:016x}")
                del self.datapaths[datapath.id]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Install table-miss flow entry to forward unknown packets to controller."""
        datapath = ev.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Table-miss flow entry: match everything, priority 0, send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info(f"[SDN] Installed default table-miss entry on DPID=0x{datapath.id:016x}")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=30, hard_timeout=0):
        """Helper function to install a flow rule into the switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )
        datapath.send_msg(mod)

    # ==========================================
    # Packet-In Handling & MAC Learning
    # ==========================================
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Process incoming packets sent to the controller."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # Ignore LLDP discovery packets
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        # Learn source MAC to avoid future flooding
        self.mac_to_port[dpid][src] = in_port

        # Determine output port
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # If destination is known, install flow entry with IP-level granularity if available
        if out_port != ofproto.OFPP_FLOOD:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            if ip_pkt:
                # Install specific IPv4 flow entry for fine-grained bandwidth accounting
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=ip_pkt.src,
                    ipv4_dst=ip_pkt.dst
                )
                self.add_flow(datapath, priority=10, match=match, actions=actions, idle_timeout=45)
            else:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
                self.add_flow(datapath, priority=1, match=match, actions=actions, idle_timeout=30)

        # Forward the current packet out
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    # ==========================================
    # Periodic OpenFlow Statistics Polling Loop
    # ==========================================
    def _monitor(self):
        """Periodically request Flow and Port stats from all connected switches."""
        while True:
            for dp in list(self.datapaths.values()):
                self._request_stats(dp)
            hub.sleep(self.monitor_interval)

    def _request_stats(self, datapath):
        """Send OFPFlowStatsRequest and OFPPortStatsRequest."""
        parser = datapath.ofproto_parser
        # Flow stats
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)
        # Port stats
        req_port = parser.OFPPortStatsRequest(datapath, 0, datapath.ofproto.OFPP_ANY)
        datapath.send_msg(req_port)

    # ==========================================
    # Flow Stats Reply Handler
    # ==========================================
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        """Parse switch flow reply, compute throughput/bandwidth, log to CSV."""
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        dpid_str = f"0x{dpid:016x}"

        # Filter out table-miss entry (priority 0) for active traffic display
        active_flows = [flow for flow in body if flow.priority > 0]
        if not active_flows:
            return

        self.tracker.print_flow_table_header()

        for flow in sorted(active_flows, key=lambda f: (f.match.get('in_port', 0), f.priority)):
            in_port = flow.match.get('in_port', 'ANY')
            eth_src = flow.match.get('eth_src', '*')
            eth_dst = flow.match.get('eth_dst', '*')
            ip_src = flow.match.get('ipv4_src', '*')
            ip_dst = flow.match.get('ipv4_dst', '*')
            packets = flow.packet_count
            bytes_count = flow.byte_count
            duration_sec = flow.duration_sec

            # Calculate delta and speed using tracker
            metrics = self.tracker.record_flow_stat(
                dpid=dpid,
                table_id=flow.table_id,
                in_port=str(in_port),
                eth_src=str(eth_src),
                eth_dst=str(eth_dst),
                ip_src=str(ip_src),
                ip_dst=str(ip_dst),
                packets=packets,
                bytes_count=bytes_count,
                duration_sec=duration_sec
            )

            speed_mbps = metrics["bandwidth_mbps"]
            self.tracker.print_flow_row(
                dpid_str=dpid_str,
                in_port=str(in_port),
                src_ip=str(ip_src),
                dst_ip=str(ip_dst),
                packets=packets,
                bytes_count=bytes_count,
                speed=speed_mbps
            )

        self.tracker.print_table_footer()

    # ==========================================
    # Port Stats Reply Handler
    # ==========================================
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        """Record port statistics to port CSV."""
        body = ev.msg.body
        dpid = ev.msg.datapath.id

        for stat in body:
            # Skip OFPP_LOCAL port if desired or record all
            if stat.port_no > 1000 and stat.port_no != 0xfffffffe:
                continue
            self.tracker.record_port_stat(
                dpid=dpid,
                port_no=stat.port_no,
                rx_packets=stat.rx_packets,
                tx_packets=stat.tx_packets,
                rx_bytes=stat.rx_bytes,
                tx_bytes=stat.tx_bytes,
                rx_errors=stat.rx_errors,
                tx_errors=stat.tx_errors
            )


def main():
    """Direct launcher helper when run with python3 controller.py."""
    try:
        from ryu.cmd import manager
        sys.argv.append(__file__)
        manager.main()
    except ImportError:
        print("[ERROR] Ryu SDN Framework is not installed in the current environment.")
        print("To install Ryu, run: pip install ryu")
        print("To run with Ryu Manager: ryu-manager sdn/controller.py")


if __name__ == "__main__":
    main()
