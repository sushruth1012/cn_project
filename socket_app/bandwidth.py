"""
bandwidth.py - Bandwidth and Throughput Calculation Utilities
-------------------------------------------------------------
Provides helper functions and tracker classes to compute:
- Bytes transferred (formatted in B, KB, MB, GB)
- Duration of connection / data transfer
- Bandwidth in Mbps (Megabits per second)
- Throughput in Kbps / Mbps
- Real-time rate monitoring
"""

import time
from typing import Dict, Any, Tuple


def format_bytes(byte_count: float) -> str:
    """Format raw byte counts into human-readable strings (B, KB, MB, GB)."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if byte_count < 1024.0 or unit == 'TB':
            return f"{byte_count:.2f} {unit}"
        byte_count /= 1024.0
    return f"{byte_count:.2f} B"


def format_speed(bits_per_sec: float) -> str:
    """Format raw bits per second into human-readable strings (bps, Kbps, Mbps, Gbps)."""
    for unit in ['bps', 'Kbps', 'Mbps', 'Gbps']:
        if bits_per_sec < 1000.0 or unit == 'Gbps':
            return f"{bits_per_sec:.2f} {unit}"
        bits_per_sec /= 1000.0
    return f"{bits_per_sec:.2f} bps"


def calculate_bandwidth_mbps(byte_count: int, duration_sec: float) -> float:
    """
    Calculate bandwidth in Megabits per second (Mbps).
    Formula: (bytes * 8 bits) / (duration_sec * 1,000,000 bits/Mb)
    """
    if duration_sec <= 0:
        return 0.0
    bits = byte_count * 8.0
    return round(bits / (duration_sec * 1_000_000.0), 4)


def calculate_throughput_kbps(byte_count: int, duration_sec: float) -> float:
    """
    Calculate throughput in Kilobits per second (Kbps).
    Formula: (bytes * 8 bits) / (duration_sec * 1,000 bits/Kb)
    """
    if duration_sec <= 0:
        return 0.0
    bits = byte_count * 8.0
    return round(bits / (duration_sec * 1_000.0), 2)


class BandwidthTracker:
    """
    Tracks bytes transferred over time to measure upload/download
    speed, bandwidth, throughput, and connection duration.
    """

    def __init__(self):
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.total_bytes: int = 0
        self.last_update_time: float = 0.0
        self.last_update_bytes: int = 0
        self.is_running: bool = False

    def start(self) -> None:
        """Start or reset the bandwidth timer."""
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_update_bytes = 0
        self.total_bytes = 0
        self.is_running = True

    def update(self, chunk_size: int) -> Tuple[float, float]:
        """
        Record a chunk of transferred bytes.
        Returns:
            Tuple of (instant_bandwidth_mbps, cumulative_bandwidth_mbps)
        """
        now = time.time()
        self.total_bytes += chunk_size

        # Instantaneous rate
        dt = now - self.last_update_time
        instant_speed_mbps = 0.0
        if dt > 0:
            instant_speed_mbps = calculate_bandwidth_mbps(chunk_size, dt)

        self.last_update_time = now
        self.last_update_bytes = self.total_bytes

        # Cumulative rate so far
        total_dt = now - self.start_time
        cum_speed_mbps = calculate_bandwidth_mbps(self.total_bytes, total_dt)

        return instant_speed_mbps, cum_speed_mbps

    def stop(self) -> Dict[str, Any]:
        """
        Stop tracking and return final summary metrics.
        """
        self.end_time = time.time()
        self.is_running = False
        duration = max(self.end_time - self.start_time, 0.0001)

        bandwidth_mbps = calculate_bandwidth_mbps(self.total_bytes, duration)
        throughput_kbps = calculate_throughput_kbps(self.total_bytes, duration)

        return {
            "total_bytes": self.total_bytes,
            "duration_sec": round(duration, 4),
            "bandwidth_mbps": bandwidth_mbps,
            "throughput_kbps": throughput_kbps,
            "formatted_bytes": format_bytes(self.total_bytes),
            "formatted_bandwidth": format_speed(bandwidth_mbps * 1_000_000),
            "formatted_throughput": format_speed(throughput_kbps * 1_000)
        }
