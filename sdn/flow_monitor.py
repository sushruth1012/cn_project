"""
flow_monitor.py - Ryu SDN Flow & Port Statistics Monitoring Helper
------------------------------------------------------------------
Calculates real-time packet rates, byte transfer rates, bandwidth (Mbps),
formats console output tables, and exports flow/port metrics to CSV.
"""

import os
import csv
import time
import threading
from datetime import datetime
from typing import Dict, Tuple, Optional

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
FLOW_CSV_PATH = os.path.join(LOG_DIR, "sdn_flow_stats.csv")
PORT_CSV_PATH = os.path.join(LOG_DIR, "sdn_port_stats.csv")

FLOW_CSV_HEADERS = [
    "timestamp",
    "dpid",
    "table_id",
    "in_port",
    "eth_src",
    "eth_dst",
    "ip_src",
    "ip_dst",
    "packets",
    "bytes",
    "delta_bytes",
    "duration_sec",
    "bandwidth_mbps",
    "packet_rate_pps"
]

PORT_CSV_HEADERS = [
    "timestamp",
    "dpid",
    "port_no",
    "rx_packets",
    "tx_packets",
    "rx_bytes",
    "tx_bytes",
    "rx_bandwidth_mbps",
    "tx_bandwidth_mbps",
    "rx_errors",
    "tx_errors"
]


class FlowStatsTracker:
    """
    Maintains historical flow & port counters across polling intervals to compute
    instantaneous delta bytes, packet rates, and bandwidth.
    """

    def __init__(self, flow_csv: str = FLOW_CSV_PATH, port_csv: str = PORT_CSV_PATH):
        self.flow_csv = flow_csv
        self.port_csv = port_csv
        self._lock = threading.Lock()

        # Cache previous flow counts: key -> (timestamp, byte_count, packet_count)
        self.prev_flow_stats: Dict[Tuple, Tuple[float, int, int]] = {}
        # Cache previous port counts: (dpid, port_no) -> (timestamp, rx_bytes, tx_bytes)
        self.prev_port_stats: Dict[Tuple[int, int], Tuple[float, int, int]] = {}

        self._init_csvs()

    def _init_csvs(self) -> None:
        """Create CSV directories and headers if not present."""
        os.makedirs(os.path.dirname(self.flow_csv), exist_ok=True)

        with self._lock:
            if not os.path.exists(self.flow_csv) or os.path.getsize(self.flow_csv) == 0:
                with open(self.flow_csv, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(FLOW_CSV_HEADERS)

            if not os.path.exists(self.port_csv) or os.path.getsize(self.port_csv) == 0:
                with open(self.port_csv, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(PORT_CSV_HEADERS)

    def record_flow_stat(
        self,
        dpid: int,
        table_id: int,
        in_port: str,
        eth_src: str,
        eth_dst: str,
        ip_src: str,
        ip_dst: str,
        packets: int,
        bytes_count: int,
        duration_sec: int
    ) -> Dict[str, float]:
        """
        Record and calculate delta bandwidth for an OpenFlow flow entry.
        """
        now = time.time()
        key = (dpid, table_id, in_port, eth_src, eth_dst, ip_src, ip_dst)

        delta_bytes = 0
        delta_packets = 0
        bandwidth_mbps = 0.0
        packet_rate = 0.0

        if key in self.prev_flow_stats:
            prev_time, prev_bytes, prev_packets = self.prev_flow_stats[key]
            dt = max(now - prev_time, 0.001)
            delta_bytes = max(0, bytes_count - prev_bytes)
            delta_packets = max(0, packets - prev_packets)

            # Bandwidth in Mbps: (delta_bytes * 8 bits) / (dt * 1,000,000)
            bandwidth_mbps = round((delta_bytes * 8.0) / (dt * 1_000_000.0), 4)
            packet_rate = round(delta_packets / dt, 2)

        self.prev_flow_stats[key] = (now, bytes_count, packets)

        # Log row to CSV
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with open(self.flow_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp_str,
                    f"0x{dpid:016x}",
                    table_id,
                    in_port,
                    eth_src,
                    eth_dst,
                    ip_src,
                    ip_dst,
                    packets,
                    bytes_count,
                    delta_bytes,
                    duration_sec,
                    bandwidth_mbps,
                    packet_rate
                ])

        return {
            "bandwidth_mbps": bandwidth_mbps,
            "packet_rate": packet_rate,
            "delta_bytes": delta_bytes
        }

    def record_port_stat(
        self,
        dpid: int,
        port_no: int,
        rx_packets: int,
        tx_packets: int,
        rx_bytes: int,
        tx_bytes: int,
        rx_errors: int,
        tx_errors: int
    ) -> Dict[str, float]:
        """
        Record and compute switch port RX/TX bandwidth metrics.
        """
        now = time.time()
        key = (dpid, port_no)

        rx_bandwidth_mbps = 0.0
        tx_bandwidth_mbps = 0.0

        if key in self.prev_port_stats:
            prev_time, prev_rx_bytes, prev_tx_bytes = self.prev_port_stats[key]
            dt = max(now - prev_time, 0.001)

            delta_rx = max(0, rx_bytes - prev_rx_bytes)
            delta_tx = max(0, tx_bytes - prev_tx_bytes)

            rx_bandwidth_mbps = round((delta_rx * 8.0) / (dt * 1_000_000.0), 4)
            tx_bandwidth_mbps = round((delta_tx * 8.0) / (dt * 1_000_000.0), 4)

        self.prev_port_stats[key] = (now, rx_bytes, tx_bytes)

        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            with open(self.port_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp_str,
                    f"0x{dpid:016x}",
                    port_no,
                    rx_packets,
                    tx_packets,
                    rx_bytes,
                    tx_bytes,
                    rx_bandwidth_mbps,
                    tx_bandwidth_mbps,
                    rx_errors,
                    tx_errors
                ])

        return {
            "rx_bandwidth_mbps": rx_bandwidth_mbps,
            "tx_bandwidth_mbps": tx_bandwidth_mbps
        }

    @staticmethod
    def print_flow_table_header():
        print("\n" + "=" * 95)
        print(f"{'Switch DPID':<18} | {'In-Port':<8} | {'Src IP':<15} | {'Dst IP':<15} | {'Packets':<8} | {'Bytes':<10} | {'Speed (Mbps)':<12}")
        print("-" * 95)

    @staticmethod
    def print_flow_row(dpid_str: str, in_port: str, src_ip: str, dst_ip: str, packets: int, bytes_count: int, speed: float):
        print(f"{dpid_str:<18} | {str(in_port):<8} | {src_ip:<15} | {dst_ip:<15} | {packets:<8} | {bytes_count:<10} | {speed:<12.3f}")

    @staticmethod
    def print_table_footer():
        print("=" * 95 + "\n")
