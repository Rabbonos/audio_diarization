#!/usr/bin/env python3
"""
RQ Worker with Resource Management
Handles audio transcription tasks with intelligent resource allocation
"""

import sys
import os
import asyncio
import signal
import time
from datetime import datetime
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rq import Worker, Connection
import redis
from src.config import settings
from src.services.audio_processor import AudioProcessor
from src.services.resource_manager import ResourceManager
from src.services.format_service import FormatService

# Initialize Redis connection
redis_conn = redis.from_url(settings.redis_url, decode_responses=True)

# Initialize resource manager
resource_manager = ResourceManager()

# Initialize format service
format_service = FormatService()

def process_audio_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process audio transcription task with resource management
    This function runs in the RQ worker process
    """
    try:
        # Register this worker
        worker_id = f"worker_{os.getpid()}_{int(time.time())}"
        resource_manager.register_worker(worker_id)
        
        print(f"Worker {worker_id} starting task: {task_data.get('task_id')}")
        
        # Extract task parameters
        task_id = task_data.get('task_id')
        file_path = task_data.get('file_path')
        language = task_data.get('language', 'auto')
        model = task_data.get('model', 'medium')
        format_type = task_data.get('format', 'json')
        diarization = task_data.get('diarization', True)
        
        # Create progress callback for Redis updates
        def progress_callback(progress: float, message: str = ""):
            try:
                redis_conn.hset(f"task:{task_id}:progress", mapping={
                    "progress": progress,
                    "message": message,
                    "updated_at": datetime.now().isoformat()
                })
            except Exception as e:
                print(f"Failed to update progress: {e}")
        
        # Initialize audio processor
        processor = AudioProcessor()
        
        # Process audio (this is async, so we need to run it in event loop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Process the audio
            result = loop.run_until_complete(
                processor.process_audio_sync(
                    file_path=file_path,
                    language=language,
                    model=model,
                    format_type=format_type,
                    diarization=diarization,
                    task_id=task_id,
                    progress_callback=progress_callback
                )
            )
            
            # Convert to requested format
            if format_type != 'raw':
                formatted_result = loop.run_until_complete(
                    format_service.convert_to_format(result, format_type, task_id)
                )
                result['formatted_output'] = formatted_result
            
            # Store result in Redis
            redis_conn.hset(f"task:{task_id}:result", mapping={
                "status": "completed",
                "result": str(result),  # Convert to string for Redis storage
                "completed_at": datetime.now().isoformat()
            })
            
            progress_callback(100.0, "Task completed successfully")
            
            print(f"Worker {worker_id} completed task: {task_id}")
            return result
            
        finally:
            loop.close()
            # Cleanup: Unregister worker
            resource_manager.unregister_worker(worker_id)
            
    except Exception as e:
        print(f"Worker {worker_id} error: {str(e)}")
        
        # Store error in Redis
        try:
            redis_conn.hset(f"task:{task_id}:result", mapping={
                "status": "error",
                "error": str(e),
                "failed_at": datetime.now().isoformat()
            })
        except:
            pass
        
        # Cleanup on error
        try:
            resource_manager.unregister_worker(worker_id)
        except:
            pass
        
        raise

def graceful_shutdown(signum, frame):
    """Handle graceful shutdown"""
    print(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

def main():
    """Main worker process"""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)
    
    print("Starting RQ worker with resource management...")
    print(f"Redis: {settings.redis_url}")
    print(f"Queue: {settings.task_queue}")
    
    # Start the worker
    with Connection(redis_conn):
        worker = Worker([settings.task_queue], connection=redis_conn)
        
        # Add custom exception handler
        def handle_exception(job, exc_type, exc_value, traceback):
            print(f"Job {job.id} failed: {exc_value}")
            return False
        
        worker.push_exc_handler(handle_exception)
        
        print("Worker started. Waiting for tasks...")
        worker.work()

if __name__ == "__main__":
    main()