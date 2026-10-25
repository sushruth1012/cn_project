"""
client.py - Bandwidth Meter Socket Client
-----------------------------------------
Connects to the BandwidthServer, performs upload/download or UDP throughput tests,
measures transmission rates, and outputs metrics to terminal and CSV.
Supports single or multi-threaded concurrent client traffic generation.
"""

import socket
import argparse
import json
import time
import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bandwidth import BandwidthTracker, format_bytes, format_speed
from logger import TrafficLogger


class BandwidthClient:
    """
    Client for running TCP upload/download or UDP traffic tests against BandwidthServer.
    """

    def __init__(
        self,
        server_ip: str = "127.0.0.1",
        tcp_port: int = 9999,
        udp_port: int = 9998,
        client_id: str = "client-1",
        csv_path: str = None
    ):
        self.server_ip = server_ip
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.client_id = client_id
        self.buffer_size = 64 * 1024  # 64 KB buffer
        self.logger = TrafficLogger(csv_path) if csv_path else TrafficLogger()

    # ==========================================
    # TCP Upload Mode
    # ==========================================
    def run_tcp_upload(self, size_mb: float = 10.0) -> dict:
        """
        Upload test: Stream bytes from client to server and compute client-side upload rate.
        """
        target_bytes = int(size_mb * 1024 * 1024)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tracker = BandwidthTracker()

        TrafficLogger.console_log("CLIENT-UPLOAD", f"Connecting to {self.server_ip}:{self.tcp_port} as [{self.client_id}]...")
        try:
            sock.connect((self.server_ip, self.tcp_port))
            local_ip, local_port = sock.getsockname()

            # 1. Send handshake control header
            header = json.dumps({
                "client_id": self.client_id,
                "mode": "UPLOAD",
                "target_bytes": target_bytes
            }) + "\n"
            sock.sendall(header.encode("utf-8"))

            # 2. Wait for server READY acknowledgment
            ack = sock.recv(1024)
            if b"READY" not in ack:
                raise RuntimeError("Server did not acknowledge upload readiness.")

            TrafficLogger.console_log(
                "CLIENT-UPLOAD",
                f"Starting upload of {format_bytes(target_bytes)}..."
            )

            # 3. Stream data payload
            tracker.start()
            chunk = b"A" * self.buffer_size
            sent_bytes = 0

            while sent_bytes < target_bytes:
                to_send = min(self.buffer_size, target_bytes - sent_bytes)
                if to_send == self.buffer_size:
                    sock.sendall(chunk)
                else:
                    sock.sendall(b"A" * to_send)
                sent_bytes += to_send
                tracker.update(to_send)

            metrics = tracker.stop()

            # 4. Read server-side summary acknowledgment
            sock.settimeout(5.0)
            server_reply = sock.recv(2048).decode("utf-8")
            server_metrics = {}
            if server_reply:
                try:
                    server_metrics = json.loads(server_reply.strip())
                except Exception:
                    pass

            self._print_summary("TCP UPLOAD", metrics, sent_bytes, 0)

            # Log to client-side CSV
            self.logger.log_record(
                client_id=self.client_id,
                client_ip=local_ip,
                client_port=local_port,
                protocol="TCP",
                mode="UPLOAD",
                bytes_sent=sent_bytes,
                bytes_received=0,
                duration_sec=metrics["duration_sec"],
                bandwidth_mbps=metrics["bandwidth_mbps"],
                throughput_kbps=metrics["throughput_kbps"],
                status="SUCCESS"
            )

            metrics["server_metrics"] = server_metrics
            return metrics

        except Exception as e:
            TrafficLogger.console_log("CLIENT-ERROR", f"Upload test failed: {e}")
            return {"status": "ERROR", "error": str(e)}
        finally:
            try:
                sock.close()
            except Exception:
                pass

    # ==========================================
    # TCP Download Mode
    # ==========================================
    def run_tcp_download(self, size_mb: float = 10.0) -> dict:
        """
        Download test: Request server to stream bytes to client and measure download rate.
        """
        target_bytes = int(size_mb * 1024 * 1024)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tracker = BandwidthTracker()

        TrafficLogger.console_log("CLIENT-DOWNLOAD", f"Connecting to {self.server_ip}:{self.tcp_port} as [{self.client_id}]...")
        try:
            sock.connect((self.server_ip, self.tcp_port))
            local_ip, local_port = sock.getsockname()

            # 1. Send handshake control header
            header = json.dumps({
                "client_id": self.client_id,
                "mode": "DOWNLOAD",
                "target_bytes": target_bytes
            }) + "\n"
            sock.sendall(header.encode("utf-8"))

            # 2. Wait for server READY acknowledgment
            ack = sock.recv(1024)
            if b"READY" not in ack:
                raise RuntimeError("Server did not acknowledge download readiness.")

            TrafficLogger.console_log(
                "CLIENT-DOWNLOAD",
                f"Starting download of {format_bytes(target_bytes)}..."
            )

            # 3. Read incoming data stream
            tracker.start()
            received_bytes = 0

            while received_bytes < target_bytes:
                to_read = min(self.buffer_size, target_bytes - received_bytes)
                data = sock.recv(to_read)
                if not data:
                    break
                received_bytes += len(data)
                tracker.update(len(data))

            metrics = tracker.stop()
            self._print_summary("TCP DOWNLOAD", metrics, 0, received_bytes)

            # Log to client-side CSV
            self.logger.log_record(
                client_id=self.client_id,
                client_ip=local_ip,
                client_port=local_port,
                protocol="TCP",
                mode="DOWNLOAD",
                bytes_sent=0,
                bytes_received=received_bytes,
                duration_sec=metrics["duration_sec"],
                bandwidth_mbps=metrics["bandwidth_mbps"],
                throughput_kbps=metrics["throughput_kbps"],
                status="SUCCESS"
            )

            return metrics

        except Exception as e:
            TrafficLogger.console_log("CLIENT-ERROR", f"Download test failed: {e}")
            return {"status": "ERROR", "error": str(e)}
        finally:
            try:
                sock.close()
            except Exception:
                pass

    # ==========================================
    # UDP Burst Mode
    # ==========================================
    def run_udp_test(self, packet_count: int = 1000, packet_size: int = 1024) -> dict:
        """
        UDP test: Send a high-speed datagram burst to measure packet delivery and rate.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tracker = BandwidthTracker()

        TrafficLogger.console_log(
            "CLIENT-UDP",
            f"Sending UDP burst to {self.server_ip}:{self.udp_port} [{packet_count} packets x {packet_size}B]..."
        )

        try:
            # Send burst handshake
            start_msg = f"UDP_START:{json.dumps({'client_id': self.client_id, 'packet_count': packet_count, 'packet_size': packet_size})}".encode("utf-8")
            sock.sendto(start_msg, (self.server_ip, self.udp_port))
            time.sleep(0.01)

            tracker.start()
            payload = b"U" * packet_size
            total_sent = 0

            for _ in range(packet_count):
                sock.sendto(payload, (self.server_ip, self.udp_port))
                total_sent += packet_size
                tracker.update(packet_size)

            metrics = tracker.stop()

            # Await server summary report
            sock.settimeout(3.0)
            try:
                resp, _ = sock.recvfrom(4096)
                server_summary = json.loads(resp.decode("utf-8"))
                TrafficLogger.console_log("CLIENT-UDP", f"Server feedback: {server_summary}")
            except socket.timeout:
                server_summary = {}

            self._print_summary("UDP BURST", metrics, total_sent, 0)

            self.logger.log_record(
                client_id=self.client_id,
                client_ip="local",
                client_port=0,
                protocol="UDP",
                mode="BURST",
                bytes_sent=total_sent,
                bytes_received=0,
                duration_sec=metrics["duration_sec"],
                bandwidth_mbps=metrics["bandwidth_mbps"],
                throughput_kbps=metrics["throughput_kbps"],
                status="SUCCESS"
            )

            return metrics
        except Exception as e:
            TrafficLogger.console_log("CLIENT-ERROR", f"UDP test failed: {e}")
            return {"status": "ERROR", "error": str(e)}
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _print_summary(self, title: str, metrics: dict, bytes_sent: int, bytes_recv: int) -> None:
        """Print formatted results table to stdout."""
        print("\n" + "=" * 55)
        print(f"       BANDWIDTH METER TEST SUMMARY - {title}")
        print("=" * 55)
        print(f" Client ID       : {self.client_id}")
        print(f" Target Server   : {self.server_ip}:{self.tcp_port}")
        print(f" Bytes Sent      : {format_bytes(bytes_sent)} ({bytes_sent:,} B)")
        print(f" Bytes Received  : {format_bytes(bytes_recv)} ({bytes_recv:,} B)")
        print(f" Duration        : {metrics.get('duration_sec', 0):.4f} seconds")
        print(f" Bandwidth       : {metrics.get('bandwidth_mbps', 0):.2f} Mbps")
        print(f" Throughput      : {metrics.get('throughput_kbps', 0):.2f} Kbps")
        print("=" * 55 + "\n")


def run_concurrent_clients(
    server_ip: str,
    tcp_port: int,
    num_clients: int,
    mode: str,
    size_mb: float,
    csv_path: str = None
) -> None:
    """Spawns multiple threads to simulate concurrent clients."""
    threads = []
    print(f"\n[INFO] Launching {num_clients} concurrent client threads...")

    def client_worker(cid: int):
        client = BandwidthClient(
            server_ip=server_ip,
            tcp_port=tcp_port,
            client_id=f"concurrent-client-{cid}",
            csv_path=csv_path
        )
        if mode.lower() == "upload":
            client.run_tcp_upload(size_mb=size_mb)
        elif mode.lower() == "download":
            client.run_tcp_download(size_mb=size_mb)
        elif mode.lower() == "udp":
            client.run_udp_test(packet_count=int(size_mb * 500))

    for i in range(1, num_clients + 1):
        t = threading.Thread(target=client_worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("[INFO] All concurrent client transfers completed.\n")


def main():
    parser = argparse.ArgumentParser(description="Bandwidth Meter Socket Client")
    parser.add_argument("--server", type=str, default="127.0.0.1", help="Server IP address (default: 127.0.0.1)")
    parser.add_argument("--tcp-port", type=int, default=9999, help="Server TCP port (default: 9999)")
    parser.add_argument("--udp-port", type=int, default=9998, help="Server UDP port (default: 9998)")
    parser.add_argument("--mode", type=str, choices=["upload", "download", "udp", "both"], default="upload",
                        help="Transfer mode: upload, download, udp, or both (default: upload)")
    parser.add_argument("--size", type=float, default=5.0, help="Payload size in MB (default: 5.0 MB)")
    parser.add_argument("--client-id", type=str, default="client-1", help="Identifier for this client")
    parser.add_argument("--threads", type=int, default=1, help="Number of concurrent client threads (default: 1)")
    parser.add_argument("--csv", type=str, default=None, help="Custom path to CSV log file")

    args = parser.parse_args()

    if args.threads > 1:
        run_concurrent_clients(
            server_ip=args.server,
            tcp_port=args.tcp_port,
            num_clients=args.threads,
            mode=args.mode,
            size_mb=args.size,
            csv_path=args.csv
        )
    else:
        client = BandwidthClient(
            server_ip=args.server,
            tcp_port=args.tcp_port,
            udp_port=args.udp_port,
            client_id=args.client_id,
            csv_path=args.csv
        )

        if args.mode == "upload":
            client.run_tcp_upload(size_mb=args.size)
        elif args.mode == "download":
            client.run_tcp_download(size_mb=args.size)
        elif args.mode == "udp":
            client.run_udp_test(packet_count=int(args.size * 500))
        elif args.mode == "both":
            print("\n--- PHASE 1: TCP UPLOAD TEST ---")
            client.run_tcp_upload(size_mb=args.size)
            time.sleep(1)
            print("\n--- PHASE 2: TCP DOWNLOAD TEST ---")
            client.run_tcp_download(size_mb=args.size)


if __name__ == "__main__":
    main()
