#!/usr/bin/env python3
"""
RQ Worker for processing transcription tasks
"""
import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

from rq import Worker
import redis
from config import settings

def main():
    """Main worker entry point"""
    # Connect to Redis
    redis_conn = redis.from_url(settings.redis_url)
    
    # Create worker with specific queue (no Connection context manager needed in RQ 2.x)
    worker = Worker([settings.task_queue], connection=redis_conn)
    print("Starting RQ worker for transcription tasks...")
    print(f"Connected to Redis at {settings.redis_url}")
    print(f"Listening on queue: {settings.task_queue}")
    print("Worker is ready to process tasks. Press Ctrl+C to stop.")
    
    # Start the worker
    worker.work()

if __name__ == "__main__":
    main()