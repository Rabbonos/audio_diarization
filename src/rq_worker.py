#!/usr/bin/env python3
"""
RQ Worker for processing transcription tasks
Each worker processes only ONE task at a time for GPU memory safety
"""
import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

from rq import Worker
import redis
from config import settings
from services.database_service import db_service
from utils.logger import get_logger

logger = get_logger("rq_worker")

def main():
    """Main worker entry point"""
    # Initialize database BEFORE processing any tasks
    try:
        db_service.initialize()
        logger.info("✅ Database initialized in RQ worker")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database in RQ worker: {e}")
        sys.exit(1)
    
    # Connect to Redis
    redis_conn = redis.from_url(settings.redis_url)
    
    # Create worker with specific queue
    # CRITICAL: burst=False means worker stays alive and processes tasks sequentially
    # name parameter helps identify individual workers in logs
    worker_name = f"worker-{os.getpid()}"
    
    worker = Worker(
        [settings.task_queue],
        connection=redis_conn,
        name=worker_name
    )
    
    print("=" * 60)
    print(f"Starting RQ Worker: {worker_name}")
    print("=" * 60)
    print(f"Connected to Redis: {settings.redis_url}")
    print(f"Listening on queue: {settings.task_queue}")
    print(f"Tasks per worker: 1 (RQ workers are single-threaded by design)")
    print(f"Task Timeout: {settings.task_timeout}s")
    print(f"Model Cache: {settings.model_cache_dir} (readonly)")
    print(f"Total workers: Managed by docker-compose replicas")
    print("=" * 60)
    print("Worker is ready to process tasks. Press Ctrl+C to stop.")
    print("=" * 60)
    
    # Start the worker - this blocks and processes tasks one at a time
    worker.work(
        burst=False,  # Don't exit after finishing jobs
        logging_level="INFO",
        max_jobs=None,  # No limit on number of jobs
        with_scheduler=False  # We don't use scheduled jobs
    )

if __name__ == "__main__":
    main()