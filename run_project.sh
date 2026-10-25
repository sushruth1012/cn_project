#!/usr/bin/env bash
# ==============================================================================
# run_project.sh - Automated Runner for BandwidthMeter & Traffic Analyzer
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Color Codes for Terminal Output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${BLUE}==============================================================================${NC}"
    echo -e "${BLUE}   BANDWIDTH METER & TRAFFIC ANALYZER (TCP/UDP + RYU SDN + MININET)          ${NC}"
    echo -e "${BLUE}==============================================================================${NC}"
}

clean_environment() {
    echo -e "\n${YELLOW}[CLEAN] Cleaning previous Mininet topologies and background processes...${NC}"
    sudo mn -c > /dev/null 2>&1 || true
    pkill -f "ryu-manager" > /dev/null 2>&1 || true
    pkill -f "controller.py" > /dev/null 2>&1 || true
    pkill -f "server.py" > /dev/null 2>&1 || true
    echo -e "${GREEN}[OK] Clean complete.${NC}"
}

run_local_demo() {
    echo -e "\n${YELLOW}>>> RUNNING LOCAL MULTI-CLIENT SOCKET EXPERIMENT <<<${NC}"
    echo -e "${BLUE}Step 1: Starting Multi-threaded Bandwidth Server...${NC}"
    python3 socket_app/server.py --host 127.0.0.1 --tcp-port 9999 --udp-port 9998 > /dev/null 2>&1 &
    SERVER_PID=$!
    sleep 2

    echo -e "${BLUE}Step 2: Generating Traffic from Multiple Concurrent Clients...${NC}"
    echo -e "  -> Client 1: TCP Upload (8 MB)..."
    python3 socket_app/client.py --server 127.0.0.1 --mode upload --size 8 --client-id "client-1"

    echo -e "  -> Client 2: TCP Download (12 MB)..."
    python3 socket_app/client.py --server 127.0.0.1 --mode download --size 12 --client-id "client-2"

    echo -e "  -> Client 3: UDP Burst (2000 packets)..."
    python3 socket_app/client.py --server 127.0.0.1 --mode udp --size 4 --client-id "client-3"

    echo -e "  -> Clients 4 & 5: Concurrent Traffic Generation..."
    python3 socket_app/client.py --server 127.0.0.1 --mode upload --size 6 --threads 2

    echo -e "${BLUE}Step 3: Stopping Local Server (PID: ${SERVER_PID})...${NC}"
    kill $SERVER_PID 2>/dev/null || true

    echo -e "${BLUE}Step 4: Running Traffic Log Analyzer...${NC}"
    python3 analyzer/analyzer.py

    echo -e "${BLUE}Step 5: Generating Analytical Performance Graphs...${NC}"
    python3 analyzer/graphs.py

    echo -e "\n${GREEN}[SUCCESS] Local demo completed. Review results in 'results/' and 'logs/'.${NC}"
}

run_mininet_sdn_demo() {
    echo -e "\n${YELLOW}>>> RUNNING COMPLETE MININET + RYU SDN WORKFLOW <<<${NC}"
    clean_environment

    echo -e "${BLUE}Step 1: Starting Ryu OpenFlow 1.3 Controller in Background...${NC}"
    ryu-manager sdn/controller.py --ofp-tcp-listen-port 6653 > logs/ryu_controller.log 2>&1 &
    RYU_PID=$!
    echo -e "Ryu Controller started (PID: ${RYU_PID}, Port: 6653). Log: logs/ryu_controller.log"
    sleep 3

    echo -e "${BLUE}Step 2: Launching Mininet Topology with Automated Traffic Tests...${NC}"
    sudo python3 sdn/topology.py --controller-port 6653 --auto-test

    echo -e "${BLUE}Step 3: Shutting Down Ryu Controller...${NC}"
    kill $RYU_PID 2>/dev/null || true

    echo -e "${BLUE}Step 4: Running Traffic Analyzer...${NC}"
    python3 analyzer/analyzer.py

    echo -e "${BLUE}Step 5: Generating Analytical Performance Graphs...${NC}"
    python3 analyzer/graphs.py

    clean_environment
    echo -e "\n${GREEN}[SUCCESS] Full SDN Mininet experiment completed!${NC}"
    echo -e "Reports generated at: ${PROJECT_DIR}/results/"
}

run_interactive_mininet() {
    echo -e "\n${YELLOW}>>> LAUNCHING INTERACTIVE MININET CLI + RYU CONTROLLER <<<${NC}"
    clean_environment

    echo -e "${BLUE}Starting Ryu Controller in Background...${NC}"
    ryu-manager sdn/controller.py --ofp-tcp-listen-port 6653 > logs/ryu_controller.log 2>&1 &
    RYU_PID=$!
    sleep 3

    echo -e "${BLUE}Starting Mininet CLI (Type 'exit' to quit)...${NC}"
    sudo python3 sdn/topology.py --controller-port 6653

    kill $RYU_PID 2>/dev/null || true
    clean_environment
}

# Main Dispatch
print_banner

case "$1" in
    local)
        run_local_demo
        ;;
    sdn)
        run_mininet_sdn_demo
        ;;
    interactive)
        run_interactive_mininet
        ;;
    clean)
        clean_environment
        ;;
    graphs)
        python3 analyzer/analyzer.py
        python3 analyzer/graphs.py
        ;;
    *)
        echo "Usage: ./run_project.sh [command]"
        echo ""
        echo "Commands:"
        echo "  local       Run the socket client-server demo locally with analyzer & graphs"
        echo "  sdn         Run the complete Mininet + Ryu SDN automated experiment (requires sudo)"
        echo "  interactive Launch Mininet CLI with Ryu Controller running (requires sudo)"
        echo "  graphs      Generate analytics summary and plots from existing logs"
        echo "  clean       Cleanup Mininet bridges, switches, and controller processes"
        echo ""
        echo "Example: ./run_project.sh local"
        exit 1
        ;;
esac
