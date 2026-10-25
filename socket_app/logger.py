"""
logger.py - CSV and Console Logging Utilities
---------------------------------------------
Provides thread-safe logging of socket traffic metrics into CSV files
and formatted console logs.
"""

import os
import csv
import threading
from datetime import datetime
from typing import Dict, Any, Optional

DEFAULT_LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
DEFAULT_CSV_PATH = os.path.join(DEFAULT_LOG_DIR, "socket_traffic.csv")

CSV_HEADERS = [
    "timestamp",
    "client_id",
    "client_ip",
    "client_port",
    "protocol",
    "mode",
    "bytes_sent",
    "bytes_received",
    "total_bytes",
    "duration_sec",
    "bandwidth_mbps",
    "throughput_kbps",
    "status"
]


class TrafficLogger:
    """
    Thread-safe logger for recording network transfer metrics to CSV.
    """
    _lock = threading.Lock()

    def __init__(self, csv_filepath: str = DEFAULT_CSV_PATH):
        self.csv_filepath = csv_filepath
        self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        """Create directory and CSV header if the log file doesn't exist."""
        log_dir = os.path.dirname(self.csv_filepath)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        if not os.path.exists(self.csv_filepath) or os.path.getsize(self.csv_filepath) == 0:
            with self._lock:
                with open(self.csv_filepath, mode='w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_HEADERS)

    def log_record(
        self,
        client_id: str,
        client_ip: str,
        client_port: int,
        protocol: str,
        mode: str,
        bytes_sent: int,
        bytes_received: int,
        duration_sec: float,
        bandwidth_mbps: float,
        throughput_kbps: float,
        status: str = "SUCCESS",
        timestamp: Optional[str] = None
    ) -> None:
        """
        Record a traffic transfer entry into the CSV file.
        """
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        total_bytes = bytes_sent + bytes_received

        row = [
            timestamp,
            client_id,
            client_ip,
            client_port,
            protocol.upper(),
            mode.upper(),
            bytes_sent,
            bytes_received,
            total_bytes,
            round(duration_sec, 4),
            round(bandwidth_mbps, 4),
            round(throughput_kbps, 2),
            status.upper()
        ]

        with self._lock:
            with open(self.csv_filepath, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)

    @staticmethod
    def console_log(tag: str, message: str) -> None:
        """Print timestamped and tagged console message."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [{tag}] {message}", flush=True)
