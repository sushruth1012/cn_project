"""
server.py - Multi-Threaded TCP/UDP Bandwidth Measurement Server
---------------------------------------------------------------
Handles concurrent client connections, measures upload/download bandwidth,
bytes sent/received, connection duration, and throughput, and logs all
connection statistics to CSV.
"""

import socket
import threading
import argparse
import json
import time
import sys
import os

# Include current directory in path for direct execution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bandwidth import BandwidthTracker, format_bytes, format_speed
from logger import TrafficLogger


class BandwidthServer:
    """
    High-performance, multi-threaded socket server capable of handling
    concurrent clients for upload and download bandwidth profiling.
    """

    def __init__(self, host: str = "0.0.0.0", tcp_port: int = 9999, udp_port: int = 9998, csv_path: str = None):
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.buffer_size = 64 * 1024  # 64 KB chunk size for efficient socket I/O
        self.logger = TrafficLogger(csv_path) if csv_path else TrafficLogger()
        self.is_running = False
        self.tcp_socket = None
        self.udp_socket = None
        self.active_connections = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start both TCP and UDP server listeners."""
        self.is_running = True

        # Start TCP listener thread
        tcp_thread = threading.Thread(target=self._run_tcp_server, name="TCP-Listener", daemon=True)
        tcp_thread.start()

        # Start UDP listener thread
        udp_thread = threading.Thread(target=self._run_udp_server, name="UDP-Listener", daemon=True)
        udp_thread.start()

        TrafficLogger.console_log("SERVER", f"Bandwidth Server running on {self.host}")
        TrafficLogger.console_log("SERVER", f"  -> TCP Port: {self.tcp_port}")
        TrafficLogger.console_log("SERVER", f"  -> UDP Port: {self.udp_port}")
        TrafficLogger.console_log("SERVER", f"Logging traffic records to: {self.logger.csv_filepath}")
        TrafficLogger.console_log("SERVER", "Press Ctrl+C to stop the server.\n")

        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            TrafficLogger.console_log("SERVER", "Shutting down Bandwidth Server...")
            self.stop()

    def stop(self) -> None:
        """Gracefully close all listening sockets."""
        self.is_running = False
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except Exception:
                pass
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception:
                pass

    # ==========================================
    # TCP Server Implementation
    # ==========================================
    def _run_tcp_server(self) -> None:
        """Initialize TCP socket and accept client connections."""
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.tcp_socket.bind((self.host, self.tcp_port))
            self.tcp_socket.listen(100)
        except Exception as e:
            TrafficLogger.console_log("TCP-ERROR", f"Failed to bind TCP port {self.tcp_port}: {e}")
            return

        while self.is_running:
            try:
                conn, addr = self.tcp_socket.accept()
                with self._lock:
                    self.active_connections += 1

                client_thread = threading.Thread(
                    target=self._handle_tcp_client,
                    args=(conn, addr),
                    daemon=True
                )
                client_thread.start()
            except socket.error:
                break
            except Exception as e:
                if self.is_running:
                    TrafficLogger.console_log("TCP-ERROR", f"Error accepting connection: {e}")

    def _handle_tcp_client(self, conn: socket.socket, addr: tuple) -> None:
        """
        Handle a single connected TCP client session.
        Negotiates control header and executes upload or download test.
        """
        client_ip, client_port = addr
        client_id = f"client-{client_ip}:{client_port}"
        mode = "UNKNOWN"
        bytes_sent = 0
        bytes_received = 0
        duration = 0.0
        bandwidth_mbps = 0.0
        throughput_kbps = 0.0
        status = "FAILED"

        tracker = BandwidthTracker()

        try:
            # 1. Receive control message header (JSON ending with newline)
            conn.settimeout(15.0)
            header_data = b""
            while b"\n" not in header_data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                header_data += chunk

            if not header_data:
                conn.close()
                return

            control_json = json.loads(header_data.decode("utf-8").strip())
            client_id = control_json.get("client_id", client_id)
            mode = control_json.get("mode", "UPLOAD").upper()
            target_bytes = int(control_json.get("target_bytes", 10 * 1024 * 1024))  # default 10MB

            TrafficLogger.console_log(
                "TCP-CONN",
                f"Accepted [{client_id}] from {client_ip}:{client_port} | Mode: {mode} | Target: {format_bytes(target_bytes)}"
            )

            # Send Ready Acknowledgment
            conn.sendall(b"READY\n")

            tracker.start()

            # 2. Execute requested transfer mode
            if mode == "UPLOAD":
                # Client uploads data to Server
                received_so_far = 0
                while received_so_far < target_bytes:
                    to_read = min(self.buffer_size, target_bytes - received_so_far)
                    data = conn.recv(to_read)
                    if not data:
                        break
                    received_so_far += len(data)
                    tracker.update(len(data))

                bytes_received = received_so_far
                metrics = tracker.stop()
                duration = metrics["duration_sec"]
                bandwidth_mbps = metrics["bandwidth_mbps"]
                throughput_kbps = metrics["throughput_kbps"]
                status = "SUCCESS"

                # Send performance report back to client
                ack_report = json.dumps({
                    "status": "COMPLETED",
                    "bytes_received": bytes_received,
                    "duration_sec": duration,
                    "bandwidth_mbps": bandwidth_mbps,
                    "throughput_kbps": throughput_kbps
                }) + "\n"
                conn.sendall(ack_report.encode("utf-8"))

            elif mode == "DOWNLOAD":
                # Server sends data to Client
                payload_chunk = b"X" * self.buffer_size
                sent_so_far = 0
                while sent_so_far < target_bytes:
                    to_send = min(self.buffer_size, target_bytes - sent_so_far)
                    if to_send == self.buffer_size:
                        conn.sendall(payload_chunk)
                    else:
                        conn.sendall(b"X" * to_send)
                    sent_so_far += to_send
                    tracker.update(to_send)

                bytes_sent = sent_so_far
                metrics = tracker.stop()
                duration = metrics["duration_sec"]
                bandwidth_mbps = metrics["bandwidth_mbps"]
                throughput_kbps = metrics["throughput_kbps"]
                status = "SUCCESS"

            TrafficLogger.console_log(
                "TCP-DONE",
                f"[{client_id}] Mode: {mode} | Data: {format_bytes(bytes_sent + bytes_received)} | "
                f"Time: {duration:.2f}s | Speed: {bandwidth_mbps:.2f} Mbps ({throughput_kbps:.2f} Kbps)"
            )

        except Exception as e:
            TrafficLogger.console_log("TCP-ERROR", f"Client [{client_id}] error: {e}")
            status = f"ERROR: {str(e)[:30]}"
            if tracker.is_running:
                metrics = tracker.stop()
                duration = metrics["duration_sec"]
                bandwidth_mbps = metrics["bandwidth_mbps"]
                throughput_kbps = metrics["throughput_kbps"]
        finally:
            with self._lock:
                self.active_connections -= 1
            try:
                conn.close()
            except Exception:
                pass

            # Log connection metrics to CSV
            self.logger.log_record(
                client_id=client_id,
                client_ip=client_ip,
                client_port=client_port,
                protocol="TCP",
                mode=mode,
                bytes_sent=bytes_sent,
                bytes_received=bytes_received,
                duration_sec=duration,
                bandwidth_mbps=bandwidth_mbps,
                throughput_kbps=throughput_kbps,
                status=status
            )

    # ==========================================
    # UDP Server Implementation
    # ==========================================
    def _run_udp_server(self) -> None:
        """Initialize UDP socket to handle datagram traffic bursts."""
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.udp_socket.bind((self.host, self.udp_port))
        except Exception as e:
            TrafficLogger.console_log("UDP-ERROR", f"Failed to bind UDP port {self.udp_port}: {e}")
            return

        udp_buffer = 65535
        while self.is_running:
            try:
                data, addr = self.udp_socket.recvfrom(udp_buffer)
                if not data:
                    continue

                # Parse simple UDP message format
                # e.g., JSON burst header or payload packet
                if data.startswith(b"UDP_START:"):
                    raw_info = data.decode("utf-8").split(":", 1)[1]
                    info = json.loads(raw_info)
                    client_id = info.get("client_id", f"{addr[0]}:{addr[1]}")
                    target_packets = info.get("packet_count", 100)
                    packet_size = info.get("packet_size", 1024)

                    TrafficLogger.console_log(
                        "UDP-START",
                        f"Incoming UDP burst from [{client_id}] | Packets: {target_packets} | Size: {packet_size}B"
                    )

                    # Track UDP incoming burst
                    tracker = BandwidthTracker()
                    tracker.start()
                    received_packets = 0
                    received_bytes = 0

                    self.udp_socket.settimeout(3.0)
                    try:
                        while received_packets < target_packets:
                            pkt, _ = self.udp_socket.recvfrom(udp_buffer)
                            received_packets += 1
                            received_bytes += len(pkt)
                            tracker.update(len(pkt))
                    except socket.timeout:
                        pass
                    finally:
                        self.udp_socket.settimeout(None)

                    metrics = tracker.stop()
                    duration = metrics["duration_sec"]
                    bandwidth_mbps = metrics["bandwidth_mbps"]
                    throughput_kbps = metrics["throughput_kbps"]

                    TrafficLogger.console_log(
                        "UDP-DONE",
                        f"[{client_id}] Received {received_packets}/{target_packets} pkts ({format_bytes(received_bytes)}) | "
                        f"Rate: {bandwidth_mbps:.2f} Mbps"
                    )

                    # Send UDP Summary reply
                    resp = json.dumps({
                        "received_packets": received_packets,
                        "received_bytes": received_bytes,
                        "duration_sec": duration,
                        "bandwidth_mbps": bandwidth_mbps
                    }).encode("utf-8")
                    self.udp_socket.sendto(resp, addr)

                    # Log to CSV
                    self.logger.log_record(
                        client_id=client_id,
                        client_ip=addr[0],
                        client_port=addr[1],
                        protocol="UDP",
                        mode="BURST",
                        bytes_sent=0,
                        bytes_received=received_bytes,
                        duration_sec=duration,
                        bandwidth_mbps=bandwidth_mbps,
                        throughput_kbps=throughput_kbps,
                        status="SUCCESS" if received_packets == target_packets else "PARTIAL"
                    )

            except socket.error:
                break
            except Exception as e:
                if self.is_running:
                    TrafficLogger.console_log("UDP-ERROR", f"UDP error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Bandwidth Meter Socket Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--tcp-port", type=int, default=9999, help="TCP port (default: 9999)")
    parser.add_argument("--udp-port", type=int, default=9998, help="UDP port (default: 9998)")
    parser.add_argument("--csv", type=str, default=None, help="Custom path to output CSV log file")

    args = parser.parse_args()

    server = BandwidthServer(
        host=args.host,
        tcp_port=args.tcp_port,
        udp_port=args.udp_port,
        csv_path=args.csv
    )
    server.start()


if __name__ == "__main__":
    main()
