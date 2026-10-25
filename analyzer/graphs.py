"""
graphs.py - Visualization and Graph Generation for Bandwidth & Traffic Analytics
--------------------------------------------------------------------------------
Generates high-resolution graphical plots from logged socket and SDN flow statistics:
  1. Bandwidth over time / per connection (Mbps)
  2. Throughput comparison across clients (Kbps)
  3. Traffic volume breakdown by client and mode (MB)
  4. OpenFlow flow rates and packet rates
  5. Comprehensive Performance Dashboard
All generated figures are saved directly into the results/ folder.
"""

import os
import sys
import csv
from collections import defaultdict
import matplotlib
# Use Agg backend for headless / server environments without display
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOCKET_LOG_PATH = os.path.join(PROJECT_ROOT, "logs", "socket_traffic.csv")
FLOW_LOG_PATH = os.path.join(PROJECT_ROOT, "logs", "sdn_flow_stats.csv")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")


class GraphGenerator:
    """
    Renders and exports graphical charts from socket & SDN traffic CSVs.
    """

    def __init__(self, socket_csv: str = SOCKET_LOG_PATH, flow_csv: str = FLOW_LOG_PATH):
        self.socket_csv = socket_csv
        self.flow_csv = flow_csv
        os.makedirs(RESULTS_DIR, exist_ok=True)
        # Configure chart appearance
        plt.style.use('ggplot')
        plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
        plt.rcParams['font.size'] = 10
        plt.rcParams['figure.autolayout'] = True

    def load_socket_records(self) -> list:
        """Loads and cleans socket CSV data into list of records."""
        if not os.path.exists(self.socket_csv):
            print(f"[WARN] File not found: {self.socket_csv}")
            return []

        records = []
        try:
            with open(self.socket_csv, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        record = {
                            "timestamp": row.get("timestamp", ""),
                            "client_id": row.get("client_id", "unknown"),
                            "protocol": row.get("protocol", "TCP"),
                            "mode": row.get("mode", "UPLOAD"),
                            "bytes_sent": float(row.get("bytes_sent", 0) or 0),
                            "bytes_received": float(row.get("bytes_received", 0) or 0),
                            "total_bytes": float(row.get("total_bytes", 0) or 0),
                            "total_mb": float(row.get("total_bytes", 0) or 0) / (1024 * 1024),
                            "duration_sec": float(row.get("duration_sec", 0.0) or 0.0),
                            "bandwidth_mbps": float(row.get("bandwidth_mbps", 0.0) or 0.0),
                            "throughput_kbps": float(row.get("throughput_kbps", 0.0) or 0.0),
                            "status": row.get("status", "SUCCESS")
                        }
                        records.append(record)
                    except ValueError:
                        continue
        except Exception as e:
            print(f"[ERROR] Failed to read {self.socket_csv}: {e}")
        return records

    def load_flow_records(self) -> list:
        """Loads flow statistics CSV."""
        if not os.path.exists(self.flow_csv):
            return []

        records = []
        try:
            with open(self.flow_csv, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        records.append({
                            "timestamp": row.get("timestamp", ""),
                            "dpid": row.get("dpid", ""),
                            "in_port": row.get("in_port", ""),
                            "packets": int(float(row.get("packets", 0) or 0)),
                            "bytes": int(float(row.get("bytes", 0) or 0)),
                            "delta_bytes": int(float(row.get("delta_bytes", 0) or 0)),
                            "bandwidth_mbps": float(row.get("bandwidth_mbps", 0.0) or 0.0),
                            "packet_rate_pps": float(row.get("packet_rate_pps", 0.0) or 0.0)
                        })
                    except ValueError:
                        continue
        except Exception:
            pass
        return records

    def plot_bandwidth_timeline(self, records: list) -> str:
        """Plot bandwidth (Mbps) for each connection event."""
        out_path = os.path.join(RESULTS_DIR, "bandwidth_timeline.png")
        plt.figure(figsize=(10, 5))

        x = list(range(1, len(records) + 1))
        y = [r["bandwidth_mbps"] for r in records]
        mean_bw = sum(y) / len(y) if y else 0.0
        max_bw = max(y) if y else 0.0

        plt.plot(x, y, marker='o', color='#1f77b4', linewidth=2.2, label='Bandwidth (Mbps)')
        plt.axhline(mean_bw, color='red', linestyle='--', linewidth=1.5,
                    label=f"Avg Bandwidth: {mean_bw:.2f} Mbps")
        plt.axhline(max_bw, color='green', linestyle=':', linewidth=1.5,
                    label=f"Peak: {max_bw:.2f} Mbps")

        plt.title("Bandwidth Measurement Across Connection Events", fontsize=13, fontweight='bold', pad=12)
        plt.xlabel("Connection Event Sequence Index", fontsize=11)
        plt.ylabel("Bandwidth (Mbps)", fontsize=11)
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.legend(loc='best')
        plt.tight_layout()

        plt.savefig(out_path, dpi=300)
        plt.close()
        print(f"[GRAPH] Saved: {out_path}")
        return out_path

    def plot_throughput_comparison(self, records: list) -> str:
        """Bar plot of Throughput (Kbps) per client."""
        out_path = os.path.join(RESULTS_DIR, "throughput_comparison.png")
        plt.figure(figsize=(10, 5))

        client_thru = defaultdict(list)
        for r in records:
            client_thru[r["client_id"]].append(r["throughput_kbps"])

        clients = list(client_thru.keys())
        avg_thru = [sum(client_thru[c]) / len(client_thru[c]) for c in clients]

        bars = plt.bar(clients, avg_thru, color='#2ca02c', width=0.55, edgecolor='black', alpha=0.85)

        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2., height + (height * 0.01) + 10,
                     f'{height:.1f} Kbps', ha='center', va='bottom', fontsize=9, fontweight='bold')

        plt.title("Average Client Throughput Comparison", fontsize=13, fontweight='bold', pad=12)
        plt.xlabel("Client Identifier", fontsize=11)
        plt.ylabel("Average Throughput (Kbps)", fontsize=11)
        plt.xticks(rotation=20, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.6)
        plt.tight_layout()

        plt.savefig(out_path, dpi=300)
        plt.close()
        print(f"[GRAPH] Saved: {out_path}")
        return out_path

    def plot_traffic_volume(self, records: list) -> str:
        """Pie chart and stacked bar for data volume by client and transfer mode."""
        out_path = os.path.join(RESULTS_DIR, "client_traffic_breakdown.png")
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Subplot 1: Volume by Client (Pie Chart)
        client_mb = defaultdict(float)
        for r in records:
            client_mb[r["client_id"]] += r["total_mb"]

        labels = list(client_mb.keys())
        values = list(client_mb.values())

        axes[0].pie(
            values,
            labels=labels,
            autopct='%1.1f%%',
            startangle=140,
            colors=['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6'],
            wedgeprops={'edgecolor': 'white', 'linewidth': 1.5}
        )
        axes[0].set_title("Traffic Distribution by Client (Total MB)", fontsize=12, fontweight='bold')

        # Subplot 2: Bytes Sent vs Received by Transfer Mode (Bar Chart)
        mode_sent = defaultdict(float)
        mode_recv = defaultdict(float)
        for r in records:
            mode_sent[r["mode"]] += r["bytes_sent"] / (1024 * 1024)
            mode_recv[r["mode"]] += r["bytes_received"] / (1024 * 1024)

        modes = list(set(list(mode_sent.keys()) + list(mode_recv.keys())))
        indices = list(range(len(modes)))
        width = 0.35

        sent_vals = [mode_sent[m] for m in modes]
        recv_vals = [mode_recv[m] for m in modes]

        axes[1].bar([i - width/2 for i in indices], sent_vals, width=width, label='Bytes Sent (MB)', color='#2980b9', edgecolor='black')
        axes[1].bar([i + width/2 for i in indices], recv_vals, width=width, label='Bytes Received (MB)', color='#e67e22', edgecolor='black')

        axes[1].set_title("Upload vs Download Volume by Mode (MB)", fontsize=12, fontweight='bold')
        axes[1].set_ylabel("Megabytes (MB)", fontsize=11)
        axes[1].set_xlabel("Transfer Mode", fontsize=11)
        axes[1].set_xticks(indices)
        axes[1].set_xticklabels(modes)
        axes[1].legend()
        axes[1].grid(axis='y', linestyle='--', alpha=0.6)

        plt.tight_layout()
        plt.savefig(out_path, dpi=300)
        plt.close()
        print(f"[GRAPH] Saved: {out_path}")
        return out_path

    def plot_sdn_flows(self) -> str:
        """Plot OpenFlow statistics from sdn_flow_stats.csv if available."""
        flow_records = self.load_flow_records()
        if not flow_records:
            return ""

        try:
            out_path = os.path.join(RESULTS_DIR, "sdn_flow_stats.png")
            fig, ax1 = plt.subplots(figsize=(10, 5))

            indices = list(range(len(flow_records)))
            bws = [r["bandwidth_mbps"] for r in flow_records]
            pkts = [r["packets"] for r in flow_records]

            color = '#d62728'
            ax1.set_xlabel('Flow Polling Record Index', fontsize=11)
            ax1.set_ylabel('Flow Bandwidth (Mbps)', color=color, fontsize=11)
            line1 = ax1.plot(indices, bws, color=color, marker='s', label='Flow Bandwidth (Mbps)')
            ax1.tick_params(axis='y', labelcolor=color)

            ax2 = ax1.twinx()
            color = '#1f77b4'
            ax2.set_ylabel('Total Packets', color=color, fontsize=11)
            line2 = ax2.plot(indices, pkts, color=color, linestyle='--', marker='^', label='Total Packets')
            ax2.tick_params(axis='y', labelcolor=color)

            # Combine legends
            lines = line1 + line2
            labels = [l.get_label() for l in lines]
            ax1.legend(lines, labels, loc='upper left')

            plt.title("Ryu Controller OpenFlow 1.3 Flow Rate & Packet Counters", fontsize=13, fontweight='bold', pad=12)
            plt.grid(True, linestyle='--', alpha=0.4)
            plt.tight_layout()

            plt.savefig(out_path, dpi=300)
            plt.close()
            print(f"[GRAPH] Saved: {out_path}")
            return out_path
        except Exception as e:
            print(f"[WARN] Could not plot SDN flow stats: {e}")
            return ""

    def plot_master_dashboard(self, records: list) -> str:
        """Combined 4-panel analytics dashboard."""
        out_path = os.path.join(RESULTS_DIR, "bandwidth_meter_dashboard.png")
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # Panel 1: Bandwidth Timeline
        bws = [r["bandwidth_mbps"] for r in records]
        mean_bw = sum(bws) / len(bws) if bws else 0.0
        axes[0, 0].plot(range(1, len(records) + 1), bws, marker='o', color='#3498db', linewidth=2)
        axes[0, 0].axhline(mean_bw, color='red', linestyle='--', label=f"Avg: {mean_bw:.2f} Mbps")
        axes[0, 0].set_title("1. Bandwidth Timeline (Mbps)", fontweight='bold')
        axes[0, 0].set_xlabel("Event Index")
        axes[0, 0].set_ylabel("Mbps")
        axes[0, 0].legend()
        axes[0, 0].grid(True, linestyle='--', alpha=0.6)

        # Panel 2: Throughput by Client
        client_thru = defaultdict(list)
        for r in records:
            client_thru[r["client_id"]].append(r["throughput_kbps"])
        c_names = list(client_thru.keys())
        c_vals = [sum(client_thru[c]) / len(client_thru[c]) for c in c_names]
        axes[0, 1].bar(c_names, c_vals, color='#2ecc71', width=0.5, edgecolor='black')
        axes[0, 1].set_title("2. Average Throughput per Client (Kbps)", fontweight='bold')
        axes[0, 1].set_xlabel("Client ID")
        axes[0, 1].set_ylabel("Kbps")
        axes[0, 1].tick_params(axis='x', rotation=15)
        axes[0, 1].grid(axis='y', linestyle='--', alpha=0.6)

        # Panel 3: Duration vs Bytes Scatter
        durations = [r["duration_sec"] for r in records]
        mb_vals = [r["total_mb"] for r in records]
        scatter = axes[1, 0].scatter(durations, mb_vals, c=bws, cmap='viridis', s=120, edgecolors='black')
        cbar = fig.colorbar(scatter, ax=axes[1, 0])
        cbar.set_label('Bandwidth (Mbps)')
        axes[1, 0].set_title("3. Duration vs Data Transferred (MB)", fontweight='bold')
        axes[1, 0].set_xlabel("Duration (seconds)")
        axes[1, 0].set_ylabel("Total Transferred (MB)")
        axes[1, 0].grid(True, linestyle='--', alpha=0.6)

        # Panel 4: Protocol Distribution
        proto_counts = defaultdict(int)
        for r in records:
            proto_counts[r["protocol"]] += 1
        p_names = list(proto_counts.keys())
        p_vals = [proto_counts[p] for p in p_names]
        axes[1, 1].bar(p_names, p_vals, color=['#9b59b6', '#e67e22'], width=0.4, edgecolor='black')
        axes[1, 1].set_title("4. Traffic Protocol Breakdown", fontweight='bold')
        axes[1, 1].set_xlabel("Protocol")
        axes[1, 1].set_ylabel("Connection Count")
        axes[1, 1].grid(axis='y', linestyle='--', alpha=0.6)

        plt.suptitle("Bandwidth Meter & SDN Traffic Analyzer - Performance Dashboard", fontsize=16, fontweight='bold', y=1.00)
        plt.tight_layout()

        plt.savefig(out_path, dpi=300)
        plt.close()
        print(f"[GRAPH] Saved: {out_path}")
        return out_path

    def generate_all_graphs(self) -> None:
        """Generates all analytics graphs from available logs."""
        records = self.load_socket_records()
        if not records:
            print("[INFO] No data to plot yet. Generating sample graphs will occur once traffic runs.")
            return

        print("\n--- Generating Network Performance Graphs ---")
        self.plot_bandwidth_timeline(records)
        self.plot_throughput_comparison(records)
        self.plot_traffic_volume(records)
        self.plot_master_dashboard(records)
        self.plot_sdn_flows()
        print("--- All Graphs Successfully Generated in results/ ---\n")


def main():
    generator = GraphGenerator()
    generator.generate_all_graphs()


if __name__ == "__main__":
    main()
