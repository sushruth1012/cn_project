"""
topology.py - Mininet 4-Host 1-Switch Topology for BandwidthMeter
-----------------------------------------------------------------
Sets up a Software Defined Network with:
  - 4 Hosts: h1 (10.0.0.1), h2 (10.0.0.2), h3 (10.0.0.3), h4 (10.0.0.4)
  - 1 Open vSwitch (s1) running OpenFlow 1.3
  - 1 Remote Controller (Ryu) connected on 127.0.0.1:6653/6633
  - Optional link bandwidth throttling (e.g., 100 Mbps, 2ms delay)

Usage:
  sudo python3 sdn/topology.py               # Interactive Mininet CLI
  sudo python3 sdn/topology.py --auto-test   # Automated socket traffic experiment
  mn --custom sdn/topology.py --topo meter_topo --controller remote
"""

import sys
import os
import time
import argparse

try:
    from mininet.topo import Topo
    from mininet.net import Mininet
    from mininet.node import RemoteController, OVSSwitch
    from mininet.link import TCLink
    from mininet.cli import CLI
    from mininet.log import setLogLevel, info
except ImportError:
    Topo = object
    Mininet = None


class BandwidthMeterTopo(Topo):
    """
    Topology with 4 Hosts connected to 1 Open vSwitch.
         [h1] (Server: 10.0.0.1)
           |
         [s1] --- [h2] (Client 1: 10.0.0.2)
          /  \\
       [h3]  [h4] (Client 2: 10.0.0.3, Client 3: 10.0.0.4)
    """

    def build(self, link_bw: int = 100, link_delay: str = "2ms"):
        # Add Open vSwitch s1
        s1 = self.addSwitch("s1", protocols="OpenFlow13")

        # Add 4 Hosts with predefined IP and MAC addresses
        h1 = self.addHost("h1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        h2 = self.addHost("h2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
        h3 = self.addHost("h3", ip="10.0.0.3/24", mac="00:00:00:00:00:03")
        h4 = self.addHost("h4", ip="10.0.0.4/24", mac="00:00:00:00:00:04")

        # Add Links with bandwidth shaping (100 Mbps default)
        link_opts = dict(bw=link_bw, delay=link_delay)
        self.addLink(h1, s1, **link_opts)
        self.addLink(h2, s1, **link_opts)
        self.addLink(h3, s1, **link_opts)
        self.addLink(h4, s1, **link_opts)


# Export topology name for Mininet CLI custom script mode
topos = {'meter_topo': (lambda: BandwidthMeterTopo())}


def run_automated_experiment(net: Mininet, project_dir: str):
    """
    Automated traffic generation test inside Mininet:
    1. Start BandwidthServer on h1 (10.0.0.1) in background
    2. Run upload and download tests from h2, h3, and h4
    3. Conclude test and kill server
    """
    info("\n*** [EXPERIMENT] Starting Automated Socket Bandwidth Experiment ***\n")

    h1, h2, h3, h4 = net.get('h1', 'h2', 'h3', 'h4')

    server_script = os.path.join(project_dir, "socket_app", "server.py")
    client_script = os.path.join(project_dir, "socket_app", "client.py")

    info("*** Step 1: Launching Bandwidth Server on h1 (10.0.0.1:9999) ***\n")
    server_cmd = f"python3 {server_script} --host 10.0.0.1 --tcp-port 9999 > /tmp/server.log 2>&1 &"
    h1.cmd(server_cmd)
    time.sleep(2)

    info("*** Step 2: Running TCP Upload test from h2 (10 MB) ***\n")
    h2_out = h2.cmd(f"python3 {client_script} --server 10.0.0.1 --mode upload --size 10 --client-id h2")
    info(h2_out)

    info("*** Step 3: Running TCP Download test from h3 (15 MB) ***\n")
    h3_out = h3.cmd(f"python3 {client_script} --server 10.0.0.1 --mode download --size 15 --client-id h3")
    info(h3_out)

    info("*** Step 4: Running Concurrent Traffic from h4 (Upload + UDP) ***\n")
    h4_out = h4.cmd(f"python3 {client_script} --server 10.0.0.1 --mode upload --size 8 --client-id h4-upload")
    info(h4_out)
    h4_udp_out = h4.cmd(f"python3 {client_script} --server 10.0.0.1 --mode udp --size 4 --client-id h4-udp")
    info(h4_udp_out)

    info("*** Step 5: Shutting down Bandwidth Server on h1 ***\n")
    h1.cmd("pkill -f server.py")
    info("*** [EXPERIMENT] Completed successfully! Check logs/ for CSV outputs. ***\n")


def start_network(controller_ip: str = "127.0.0.1", controller_port: int = 6653, auto_test: bool = False):
    """Bootstraps Mininet network, configures OpenFlow 1.3 switch, and starts CLI/test."""
    if Mininet is None:
        print("[ERROR] Mininet python package is not installed.")
        print("Please run this script inside a Mininet-enabled Linux environment (e.g., Ubuntu/VM).")
        sys.exit(1)

    setLogLevel('info')
    topo = BandwidthMeterTopo()

    info("*** Creating Mininet Network with Remote Ryu Controller ***\n")
    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        link=TCLink,
        controller=None,
        autoSetMacs=True
    )

    # Attach Remote Ryu Controller
    c0 = net.addController(
        'c0',
        controller=RemoteController,
        ip=controller_ip,
        port=controller_port
    )

    info(f"*** Connecting to Ryu Controller at {controller_ip}:{controller_port} ***\n")
    net.start()

    # Configure OpenFlow 1.3 on switch s1
    s1 = net.get('s1')
    s1.cmd('ovs-vsctl set bridge s1 protocols=OpenFlow13')

    # Wait for controller connection
    info("*** Waiting for Open vSwitch to establish connection with Ryu... ***\n")
    time.sleep(2)

    # PingAll to warm up controller MAC learning
    info("*** Warming up ARP and MAC tables with pingAll... ***\n")
    net.pingAll()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    if auto_test:
        run_automated_experiment(net, project_root)
    else:
        info("\n*** Entering Mininet Interactive CLI. ***\n")
        info("*** You can now open xterms or run commands on hosts: ***\n")
        info("    mininet> h1 python3 socket_app/server.py --host 10.0.0.1 &\n")
        info("    mininet> h2 python3 socket_app/client.py --server 10.0.0.1 --mode upload\n")
        CLI(net)

    info("*** Stopping Mininet network... ***\n")
    net.stop()


def main():
    parser = argparse.ArgumentParser(description="Bandwidth Meter Mininet Topology")
    parser.add_argument("--controller-ip", type=str, default="127.0.0.1", help="Ryu controller IP (default: 127.0.0.1)")
    parser.add_argument("--controller-port", type=int, default=6653, help="Ryu controller OpenFlow port (default: 6653)")
    parser.add_argument("--auto-test", action="store_true", help="Run automated multi-client traffic test")

    args = parser.parse_args()
    start_network(
        controller_ip=args.controller_ip,
        controller_port=args.controller_port,
        auto_test=args.auto_test
    )


if __name__ == "__main__":
    main()
