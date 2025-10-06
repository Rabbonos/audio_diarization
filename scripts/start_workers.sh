#!/bin/bash

# Audio Diarization Service - Worker Management Script
# Manages multiple RQ workers with resource constraints

set -e

# Configuration
WORKERS=${WORKERS:-2}
WORKER_SCRIPT="worker.py"
LOG_DIR="/app/logs"
PID_DIR="/app/pids"

# Create directories
mkdir -p "$LOG_DIR" "$PID_DIR"

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

start_worker() {
    local worker_id=$1
    local log_file="$LOG_DIR/worker_${worker_id}.log"
    local pid_file="$PID_DIR/worker_${worker_id}.pid"
    
    log "Starting worker $worker_id..."
    
    # Start worker in background
    python "$WORKER_SCRIPT" > "$log_file" 2>&1 &
    local pid=$!
    
    # Save PID
    echo $pid > "$pid_file"
    
    log "Worker $worker_id started with PID $pid"
}

stop_worker() {
    local worker_id=$1
    local pid_file="$PID_DIR/worker_${worker_id}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log "Stopping worker $worker_id (PID: $pid)..."
            kill -TERM "$pid"
            
            # Wait for graceful shutdown
            local count=0
            while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
                sleep 1
                count=$((count + 1))
            done
            
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                log "Force killing worker $worker_id..."
                kill -KILL "$pid"
            fi
        fi
        rm -f "$pid_file"
    fi
}

stop_all_workers() {
    log "Stopping all workers..."
    for i in $(seq 1 $WORKERS); do
        stop_worker $i
    done
}

start_all_workers() {
    log "Starting $WORKERS workers..."
    for i in $(seq 1 $WORKERS); do
        start_worker $i
        sleep 2  # Stagger worker startup
    done
}

check_workers() {
    log "Checking worker status..."
    for i in $(seq 1 $WORKERS); do
        local pid_file="$PID_DIR/worker_${i}.pid"
        if [ -f "$pid_file" ]; then
            local pid=$(cat "$pid_file")
            if kill -0 "$pid" 2>/dev/null; then
                log "Worker $i (PID: $pid) - Running"
            else
                log "Worker $i (PID: $pid) - Dead, restarting..."
                rm -f "$pid_file"
                start_worker $i
            fi
        else
            log "Worker $i - Not running, starting..."
            start_worker $i
        fi
    done
}

cleanup() {
    log "Received signal, cleaning up..."
    stop_all_workers
    exit 0
}

# Signal handlers
trap cleanup SIGTERM SIGINT

# Main logic
case "${1:-start}" in
    start)
        log "Starting Audio Diarization Workers (Count: $WORKERS)"
        start_all_workers
        
        # Monitor workers
        while true; do
            sleep 30
            check_workers
        done
        ;;
    stop)
        stop_all_workers
        ;;
    restart)
        stop_all_workers
        sleep 2
        start_all_workers
        ;;
    status)
        check_workers
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac