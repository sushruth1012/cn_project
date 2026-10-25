# Bandwidth Meter and Traffic Analyzer using TCP/UDP Sockets & SDN (Mininet + Ryu)

A complete Computer Networks capstone / mini project that demonstrates high-performance **TCP/UDP Socket Programming** coupled with **Software Defined Networking (SDN)**. The project features concurrent socket traffic generation, bandwidth measurement, OpenFlow flow monitoring with the **Ryu Controller**, interactive simulation in **Mininet**, CSV telemetry logging, and automated graphical analysis using **Pandas** and **Matplotlib**.

---

## 🌟 Key Features

1. **Multi-Threaded Socket Engine (`socket_app/`)**:
   - High-throughput TCP Server capable of handling concurrent clients.
   - Dual-protocol support: **TCP** (Upload & Download streaming) and **UDP** (burst packet delivery).
   - Real-time measurement of:
     - Total Bytes Transferred (Formatted dynamically in B, KB, MB, GB)
     - Elapsed Duration (seconds)
     - Bandwidth (Megabits per second - Mbps)
     - Throughput (Kilobits per second - Kbps)
   - Thread-safe CSV logging of connection sessions into `logs/socket_traffic.csv`.

2. **Software Defined Networking (`sdn/`)**:
   - **4-Host, 1-Switch Topology** simulated using Mininet with Open vSwitch (`s1`).
   - Remote **Ryu Controller** (`OpenFlow 1.3`) managing packet routing, dynamic MAC learning, and table-miss flow installations.
   - **Real-Time Flow Monitoring (`flow_monitor.py`)**: Periodically sends `OFPFlowStatsRequest` and `OFPPortStatsRequest` to calculate delta bytes, packet rates, and link bandwidth utilization.
   - Outputs OpenFlow metrics directly to terminal and persists to `logs/sdn_flow_stats.csv` and `logs/sdn_port_stats.csv`.

3. **Analytics & Visualization (`analyzer/`)**:
   - **Statistical Summary (`analyzer.py`)**: Evaluates aggregate traffic, average/peak bandwidth, per-client metrics, and transfer mode breakdowns. Generates `results/summary_report.txt` and `results/summary_report.json`.
   - **Automated Plotting (`graphs.py`)**: Renders high-resolution charts:
     - Bandwidth Timeline (`results/bandwidth_timeline.png`)
     - Client Throughput Comparison (`results/throughput_comparison.png`)
     - Traffic Breakdown by Client & Mode (`results/client_traffic_breakdown.png`)
     - OpenFlow Flow Rate & Packet Counter Trends (`results/sdn_flow_stats.png`)
     - Complete 4-Panel Performance Dashboard (`results/bandwidth_meter_dashboard.png`)

---

## 🏗️ Project Architecture

```
+---------------------------------------------------------------------------------+
|                               SDN CONTROL PLANE                                 |
|                                                                                 |
|                   +---------------------------------------+                     |
|                   |        Ryu Controller (OF 1.3)        |                     |
|                   |  - MAC Learning & Flow Rules (OFPMod) |                     |
|                   |  - Periodic Polling (Stats Request)   |                     |
|                   |  - Real-time Flow Bandwidth Monitor   |                     |
|                   +-------------------+-------------------+                     |
+---------------------------------------|-----------------------------------------+
                                        | OpenFlow 1.3 Channel (TCP 6653)
+---------------------------------------|-----------------------------------------+
|                               DATA PLANE (Mininet)                              |
|                                       v                                         |
|                   +---------------------------------------+                     |
|                   |      Open vSwitch (s1) OpenFlow13     |                     |
|                   +---+---------------+---------------+---+                     |
|                       |               |               |                         |
|             Port 1    |     Port 2    |     Port 3    |     Port 4              |
|            +----------+   +-----------+   +-----------+   +----------+          |
|            |              |               |               |          |          |
|          +----+         +----+          +----+          +----+       |          |
|          | h1 |         | h2 |          | h3 |          | h4 |       |          |
|          +----+         +----+          +----+          +----+       |          |
|       (10.0.0.1)     (10.0.0.2)      (10.0.0.3)      (10.0.0.4)      |          |
+------------|--------------|---------------|---------------|---------------------+
             |              |               |               |
+------------|--------------|---------------|---------------|---------------------+
| APPLICATION LAYER         |               |               |                     |
|            v              v               v               v                     |
|     +-------------+ +-------------+ +-------------+ +-------------+             |
|     |  Bandwidth  | |  Bandwidth  | |  Bandwidth  | |  Bandwidth  |             |
|     |   Server    | |   Client    | |   Client    | | Client / UDP|             |
|     |  (server.py)| | (client.py) | | (client.py) | | (client.py) |             |
|     +------+------+ +------+------+ +------+------+ +------+------+             |
|            |               |               |               |                    |
+------------|---------------|---------------|---------------|--------------------+
             +---------------+---------------+---------------+
                             | Logs & Metrics
                             v
           +-----------------------------------+
           |    CSV Telemetry Repository       |
           |  - logs/socket_traffic.csv        |
           |  - logs/sdn_flow_stats.csv        |
           +-----------------+-----------------+
                             |
                             v
           +-----------------------------------+
           |     Analyzer & Graph Generator    |
           |  - analyzer/analyzer.py           |
           |  - analyzer/graphs.py             |
           +-----------------+-----------------+
                             |
                             v
           +-----------------------------------+
           |      Results & Visual Reports     |
           |  - results/summary_report.txt     |
           |  - results/*.png (Plots)          |
           +-----------------------------------+
```

---

## 🔄 Data Flow & Communication Lifecycle

```
Client (e.g. h2)                           Server (h1)                       Ryu Controller
      |                                         |                                  |
      |--------- TCP SYN (to 10.0.0.1:9999) --->|                                  |
      |   (Packet-In trigger if rule absent) ---+--------------------------------->|
      |                                         |                                  | (Learns MAC,
      |                                         |<-- Installs Flow Rule via OFPMod-+  Outputs Packet)
      |<-------- TCP SYN-ACK / Handshake -------|                                  |
      |                                         |                                  |
      |-- 1. JSON Header {"mode": "UPLOAD"} --->|                                  |
      |<-------- 2. "READY" Acknowledgment -----|                                  |
      |                                         |                                  |
      |-- 3. Data Chunks (64 KB stream) ------->|                                  |
      |      [BandwidthTracker measures rate]   | [BandwidthTracker measures rate] |
      |                                         |                                  |
      |                                         |--- Periodic OFPFlowStatsReq ---->|
      |                                         |<-- OFPFlowStatsReply (Bytes/Pkts)|
      |                                         |    [Calculates Flow Bandwidth]   |
      |                                         |                                  |
      |                                         |-- 4. Writes row to               |
      |<-- 5. Final Transfer Report JSON -------+      logs/socket_traffic.csv     |
      |                                                                            |
```

---

## 📂 Directory Layout

```
BandwidthMeter/
│
├── socket_app/
│   ├── server.py          # Multi-threaded TCP/UDP server with bandwidth monitoring
│   ├── client.py          # Flexible client supporting upload, download, and UDP bursts
│   ├── bandwidth.py       # Metrics calculator (Mbps, Kbps, byte formatting, timers)
│   ├── logger.py          # Thread-safe CSV and formatted console logging
│
├── sdn/
│   ├── topology.py        # Mininet 4-Host 1-Switch topology script (OF 1.3)
│   ├── controller.py      # Ryu OpenFlow 1.3 controller with dynamic flow stats polling
│   ├── flow_monitor.py    # OpenFlow stats parser, delta bandwidth tracker & CSV exporter
│
├── analyzer/
│   ├── analyzer.py        # Statistical traffic summary processor using Pandas
│   ├── graphs.py          # Matplotlib chart generator (timeline, throughput, breakdown)
│
├── logs/                  # Storage directory for CSV logs & traces
│   ├── socket_traffic.csv # Connection-level upload/download records
│   ├── sdn_flow_stats.csv # Flow-level OpenFlow byte/packet counters
│   └── sdn_port_stats.csv # Switch port RX/TX metrics
│
├── results/               # Output directory for summary reports & visual charts
│   ├── summary_report.txt
│   ├── summary_report.json
│   ├── bandwidth_timeline.png
│   ├── throughput_comparison.png
│   ├── client_traffic_breakdown.png
│   └── bandwidth_meter_dashboard.png
│
├── requirements.txt       # Python dependencies
├── run_project.sh         # All-in-one automated experiment orchestrator (Bash)
└── README.md              # Project documentation and user manual
```

---

## 🛠️ System Requirements & Prerequisites

### 1. Host Operating System
- **Linux (Ubuntu 20.04 / 22.04 LTS)** or **WSL2** or a **Virtual Machine** (VirtualBox/VMware).
  *(Note: The `socket_app/` and `analyzer/` modules are cross-platform and run on Windows/macOS/Linux. Mininet and Open vSwitch require Linux kernel support.)*

### 2. System Packages (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install -y python3 python3-pip mininet openvswitch-switch openvswitch-testcontroller net-tools
```

### 3. Python Packages
```bash
pip install -r requirements.txt
```

---

## 🚀 Execution Guide

### Option A: Complete Automated Runner (Recommended for Mininet)

Use the provided master bash script to run the entire project end-to-end:

```bash
chmod +x run_project.sh

# 1. Run local multi-client simulation (Runs on any OS without root)
./run_project.sh local

# 2. Run automated SDN Mininet experiment (Requires Linux + sudo)
./run_project.sh sdn

# 3. Launch interactive Mininet CLI with Ryu controller
./run_project.sh interactive

# 4. Generate graphs from existing logs
./run_project.sh graphs

# 5. Clean up Open vSwitch and background processes
./run_project.sh clean
```

---

### Option B: Step-by-Step Manual Execution in Mininet

#### Terminal 1: Launch Ryu Controller
```bash
ryu-manager sdn/controller.py --ofp-tcp-listen-port 6653
```
*The controller initializes, awaits switch connection, and displays live flow rate tables.*

#### Terminal 2: Start Mininet Topology
```bash
sudo python3 sdn/topology.py --controller-port 6653
```
*Mininet creates `h1`, `h2`, `h3`, `h4`, and switch `s1`, binds to the controller, and opens the `mininet>` CLI.*

#### Terminal 3 (or inside Mininet CLI): Run Socket Server & Clients
From the `mininet>` prompt:
```bash
# Start Bandwidth Server on Host 1
mininet> h1 python3 socket_app/server.py --host 10.0.0.1 --tcp-port 9999 &

# Run TCP Upload from Host 2 (10 MB payload)
mininet> h2 python3 socket_app/client.py --server 10.0.0.1 --mode upload --size 10 --client-id h2

# Run TCP Download from Host 3 (15 MB payload)
mininet> h3 python3 socket_app/client.py --server 10.0.0.1 --mode download --size 15 --client-id h3

# Run UDP Traffic Burst from Host 4
mininet> h4 python3 socket_app/client.py --server 10.0.0.1 --mode udp --size 5 --client-id h4-udp

# Run Multi-threaded Concurrent Clients from Host 2
mininet> h2 python3 socket_app/client.py --server 10.0.0.1 --mode upload --size 8 --threads 3
```

#### Terminal 4: Analyze Traffic & Generate Charts
```bash
# Print summary statistics
python3 analyzer/analyzer.py

# Generate high-resolution graphs
python3 analyzer/graphs.py
```
*All charts and text reports will be generated in `results/`.*

---

## 📊 Sample Metrics & Output Format

### Terminal Output from Bandwidth Client:
```text
=======================================================
       BANDWIDTH METER TEST SUMMARY - TCP UPLOAD
=======================================================
 Client ID       : h2
 Target Server   : 10.0.0.1:9999
 Bytes Sent      : 10.00 MB (10,485,760 B)
 Bytes Received  : 0.00 B (0 B)
 Duration        : 0.8421 seconds
 Bandwidth       : 99.61 Mbps
 Throughput      : 99612.45 Kbps
=======================================================
```

### Controller Real-Time Flow Statistics Table:
```text
===============================================================================================
Switch DPID        | In-Port  | Src IP          | Dst IP          | Packets  | Bytes      | Speed (Mbps) 
-----------------------------------------------------------------------------------------------
0x0000000000000001 | 2        | 10.0.0.2        | 10.0.0.1        | 7240     | 10582400   | 98.450      
0x0000000000000001 | 1        | 10.0.0.1        | 10.0.0.2        | 3620     | 231680     | 2.140       
===============================================================================================
```

---

## 📈 Visual Graph Artifacts in `results/`

1. **`bandwidth_timeline.png`**: Chronological line plot tracking bandwidth across successive client transfers with average and peak markers.
2. **`throughput_comparison.png`**: Bar chart comparing achieved throughput (Kbps) across distinct clients.
3. **`client_traffic_breakdown.png`**: Traffic volume distribution by host and transfer mode (Upload vs Download).
4. **`sdn_flow_stats.png`**: Dual-axis graph correlating OpenFlow byte rates with cumulative packet arrivals.
5. **`bandwidth_meter_dashboard.png`**: Comprehensive 4-panel overview summarizing the entire test suite.

---

## 💡 Code Design & Modularity

- **Decoupled Architecture**: Socket application (`socket_app/`), SDN network logic (`sdn/`), and analytical visualization (`analyzer/`) operate independently.
- **Thread Safety**: Concurrent socket workers and controller telemetry use explicit threading locks (`threading.Lock()`) for zero-collision CSV logging.
- **Defensive Error Handling**: Automatic fallback for missing directories, broken sockets, timeout management, and graceful teardown upon `Ctrl+C`.
