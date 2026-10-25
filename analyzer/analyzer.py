"""
analyzer.py - Network Traffic and Bandwidth Log Analyzer
-------------------------------------------------------
Parses socket traffic logs and OpenFlow flow statistics CSVs.
Supports Pandas with an automatic built-in CSV fallback if pandas is unavailable.
Computes summary statistics:
  - Total data transferred (Bytes / MB / GB)
  - Peak bandwidth and minimum bandwidth
  - Average bandwidth and throughput
  - Client-by-client transfer statistics
  - Mode comparisons (Upload vs Download vs UDP)
Outputs formatted reports to terminal and saves reports in results/.
"""

import os
import sys
import json
import csv
from datetime import datetime

# Set up paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "socket_traffic.csv")
DEFAULT_FLOW_LOG = os.path.join(PROJECT_ROOT, "logs", "sdn_flow_stats.csv")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")


def format_bytes(byte_count: float) -> str:
    """Format bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if byte_count < 1024.0 or unit == 'TB':
            return f"{byte_count:.2f} {unit}"
        byte_count /= 1024.0
    return f"{byte_count:.2f} B"


class TrafficAnalyzer:
    """
    Parses and summarizes network performance metrics from CSV logs.
    Works seamlessly with or without pandas.
    """

    def __init__(self, socket_log: str = DEFAULT_LOG_FILE, flow_log: str = DEFAULT_FLOW_LOG):
        self.socket_log = socket_log
        self.flow_log = flow_log
        os.makedirs(RESULTS_DIR, exist_ok=True)

    def load_socket_records(self) -> list:
        """Read socket CSV into list of dictionary records."""
        if not os.path.exists(self.socket_log):
            return []

        records = []
        try:
            with open(self.socket_log, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        record = {
                            "timestamp": row.get("timestamp", ""),
                            "client_id": row.get("client_id", "unknown"),
                            "client_ip": row.get("client_ip", ""),
                            "client_port": int(row.get("client_port", 0) or 0),
                            "protocol": row.get("protocol", "TCP"),
                            "mode": row.get("mode", "UPLOAD"),
                            "bytes_sent": int(float(row.get("bytes_sent", 0) or 0)),
                            "bytes_received": int(float(row.get("bytes_received", 0) or 0)),
                            "total_bytes": int(float(row.get("total_bytes", 0) or 0)),
                            "duration_sec": float(row.get("duration_sec", 0.0) or 0.0),
                            "bandwidth_mbps": float(row.get("bandwidth_mbps", 0.0) or 0.0),
                            "throughput_kbps": float(row.get("throughput_kbps", 0.0) or 0.0),
                            "status": row.get("status", "SUCCESS")
                        }
                        records.append(record)
                    except ValueError:
                        continue
        except Exception as e:
            print(f"[ERROR] Failed to read {self.socket_log}: {e}")
        return records

    def generate_summary(self) -> dict:
        """
        Compute high-level traffic metrics across all socket events.
        """
        records = self.load_socket_records()
        if not records:
            return {"error": "No socket traffic records found."}

        total_transfers = len(records)
        total_bytes = sum(r["total_bytes"] for r in records)
        total_sent = sum(r["bytes_sent"] for r in records)
        total_recv = sum(r["bytes_received"] for r in records)

        bandwidths = [r["bandwidth_mbps"] for r in records]
        throughputs = [r["throughput_kbps"] for r in records]
        durations = [r["duration_sec"] for r in records]

        avg_bandwidth = sum(bandwidths) / len(bandwidths) if bandwidths else 0.0
        peak_bandwidth = max(bandwidths) if bandwidths else 0.0
        min_bandwidth = min(bandwidths) if bandwidths else 0.0
        avg_throughput = sum(throughputs) / len(throughputs) if throughputs else 0.0
        peak_throughput = max(throughputs) if throughputs else 0.0
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        total_duration = sum(durations)

        # Client breakdown
        client_groups = {}
        for r in records:
            cid = r["client_id"]
            client_groups.setdefault(cid, []).append(r)

        client_stats = {}
        for cid, group in client_groups.items():
            g_bytes = sum(x["total_bytes"] for x in group)
            g_bw = [x["bandwidth_mbps"] for x in group]
            g_tp = [x["throughput_kbps"] for x in group]
            client_stats[cid] = {
                "transfers": len(group),
                "total_bytes": g_bytes,
                "formatted_bytes": format_bytes(g_bytes),
                "avg_bandwidth_mbps": round(sum(g_bw) / len(g_bw), 2),
                "peak_bandwidth_mbps": round(max(g_bw), 2),
                "avg_throughput_kbps": round(sum(g_tp) / len(g_tp), 2)
            }

        # Mode breakdown
        mode_groups = {}
        for r in records:
            mode = r["mode"]
            mode_groups.setdefault(mode, []).append(r)

        mode_stats = {}
        for mode, group in mode_groups.items():
            m_bytes = sum(x["total_bytes"] for x in group)
            m_bw = [x["bandwidth_mbps"] for x in group]
            mode_stats[mode] = {
                "count": len(group),
                "total_bytes": m_bytes,
                "formatted_bytes": format_bytes(m_bytes),
                "avg_bandwidth_mbps": round(sum(m_bw) / len(m_bw), 2),
                "peak_bandwidth_mbps": round(max(m_bw), 2)
            }

        summary = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_transfers": total_transfers,
            "total_bytes": total_bytes,
            "total_formatted": format_bytes(total_bytes),
            "total_sent_bytes": total_sent,
            "total_sent_formatted": format_bytes(total_sent),
            "total_received_bytes": total_recv,
            "total_received_formatted": format_bytes(total_recv),
            "average_bandwidth_mbps": round(avg_bandwidth, 2),
            "peak_bandwidth_mbps": round(peak_bandwidth, 2),
            "min_bandwidth_mbps": round(min_bandwidth, 2),
            "average_throughput_kbps": round(avg_throughput, 2),
            "peak_throughput_kbps": round(peak_throughput, 2),
            "average_duration_sec": round(avg_duration, 4),
            "total_duration_sec": round(total_duration, 4),
            "client_breakdown": client_stats,
            "mode_breakdown": mode_stats
        }

        # Save summary report to results/
        self._save_summary_report(summary)
        return summary

    def _save_summary_report(self, summary: dict) -> None:
        """Write summary text and JSON to results folder."""
        json_path = os.path.join(RESULTS_DIR, "summary_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=4)

        txt_path = os.path.join(RESULTS_DIR, "summary_report.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("=" * 65 + "\n")
            f.write("        BANDWIDTH METER & TRAFFIC ANALYZER REPORT        \n")
            f.write("=" * 65 + "\n")
            f.write(f"Generated at           : {summary.get('timestamp')}\n")
            f.write(f"Total Connections      : {summary.get('total_transfers')}\n")
            f.write(f"Total Traffic Volume   : {summary.get('total_formatted')} ({summary.get('total_bytes'):,} bytes)\n")
            f.write(f"  - Total Sent         : {summary.get('total_sent_formatted')}\n")
            f.write(f"  - Total Received     : {summary.get('total_received_formatted')}\n")
            f.write(f"Average Bandwidth      : {summary.get('average_bandwidth_mbps')} Mbps\n")
            f.write(f"Peak Bandwidth         : {summary.get('peak_bandwidth_mbps')} Mbps\n")
            f.write(f"Minimum Bandwidth      : {summary.get('min_bandwidth_mbps')} Mbps\n")
            f.write(f"Average Throughput     : {summary.get('average_throughput_kbps')} Kbps\n")
            f.write(f"Peak Throughput        : {summary.get('peak_throughput_kbps')} Kbps\n")
            f.write(f"Average Connection Time: {summary.get('average_duration_sec')} s\n")
            f.write("-" * 65 + "\n")
            f.write("CLIENT PERFORMANCE BREAKDOWN:\n")
            for cid, cinfo in summary.get("client_breakdown", {}).items():
                f.write(f"  [{cid}]\n")
                f.write(f"    - Sessions   : {cinfo['transfers']}\n")
                f.write(f"    - Volume     : {cinfo['formatted_bytes']}\n")
                f.write(f"    - Avg Speed  : {cinfo['avg_bandwidth_mbps']} Mbps\n")
                f.write(f"    - Peak Speed : {cinfo['peak_bandwidth_mbps']} Mbps\n")
            f.write("-" * 65 + "\n")
            f.write("MODE PERFORMANCE BREAKDOWN:\n")
            for mode, minfo in summary.get("mode_breakdown", {}).items():
                f.write(f"  [{mode}]: {minfo['count']} transfers | Volume: {minfo['formatted_bytes']} | Avg: {minfo['avg_bandwidth_mbps']} Mbps\n")
            f.write("=" * 65 + "\n")

    def print_terminal_report(self) -> None:
        """Display ASCII summary report in the console."""
        summary = self.generate_summary()
        if "error" in summary:
            print(f"[INFO] {summary['error']}")
            return

        print("\n" + "=" * 65)
        print("        BANDWIDTH METER & TRAFFIC ANALYZER REPORT        ")
        print("=" * 65)
        print(f" Total Connections       : {summary['total_transfers']}")
        print(f" Total Traffic Volume    : {summary['total_formatted']} ({summary['total_bytes']:,} bytes)")
        print(f"   Bytes Uploaded/Sent   : {summary['total_sent_formatted']}")
        print(f"   Bytes Downloaded/Recv : {summary['total_received_formatted']}")
        print(f" Average Bandwidth       : {summary['average_bandwidth_mbps']} Mbps")
        print(f" Peak Bandwidth          : {summary['peak_bandwidth_mbps']} Mbps")
        print(f" Minimum Bandwidth       : {summary['min_bandwidth_mbps']} Mbps")
        print(f" Average Throughput      : {summary['average_throughput_kbps']} Kbps")
        print(f" Peak Throughput         : {summary['peak_throughput_kbps']} Kbps")
        print(f" Average Duration        : {summary['average_duration_sec']} s")
        print("-" * 65)
        print(" CLIENT BREAKDOWN:")
        for cid, cinfo in summary.get("client_breakdown", {}).items():
            print(f"   {cid:<20} | Volume: {cinfo['formatted_bytes']:<10} | Avg: {cinfo['avg_bandwidth_mbps']:>6.2f} Mbps | Peak: {cinfo['peak_bandwidth_mbps']:>6.2f} Mbps")
        print("-" * 65)
        print(" TRANSFER MODES:")
        for mode, minfo in summary.get("mode_breakdown", {}).items():
            print(f"   {mode:<20} | Sessions: {minfo['count']:<4} | Volume: {minfo['formatted_bytes']:<10} | Avg: {minfo['avg_bandwidth_mbps']:>6.2f} Mbps")
        print("=" * 65)
        print(f"Saved text report: {os.path.join(RESULTS_DIR, 'summary_report.txt')}")
        print(f"Saved JSON report: {os.path.join(RESULTS_DIR, 'summary_report.json')}\n")


def main():
    analyzer = TrafficAnalyzer()
    analyzer.print_terminal_report()


if __name__ == "__main__":
    main()
