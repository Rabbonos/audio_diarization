"""
RQ task manager for handling background tasks using Redis Queue
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError
from ..config import settings
from ..utils.logger import get_logger
from ..utils.redis_client import get_redis_client
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError
from ..config import settings

class RQTaskManager:
    """Manages task queuing and execution using Redis Queue (RQ)"""
    
    def __init__(self):
        self.redis = get_redis_client()
        self.queue = Queue(settings.task_queue, connection=self.redis)
        self.logger = get_logger("rq_task_manager")        # Keys for task metadata
        self.task_metadata_prefix = "task_metadata:"
        self.active_tasks_key = "active_tasks"
        
    async def create_task(self, task_id: Optional[str] = None, **task_params) -> str:
        """Create a new transcription task using RQ"""
        from .audio_tasks import process_transcription_task
        
        # Enqueue the job with optional job_id (task_id)
        job = self.queue.enqueue(
            process_transcription_task,
            **task_params,
            job_id=task_id,  # Use provided task_id as job_id for consistency
            job_timeout='8h',  # 8 hour timeout
            result_ttl=86400,  # Keep result for 24 hours
            failure_ttl=3600   # Keep failed jobs for 1 hour
        )
        
        task_id = job.id
        
        # Store task metadata
        metadata = {
            "created_at": datetime.now().isoformat(),
            "status": "queued",
            "progress": 0.0,
            "message": "Task queued for processing",
            **task_params
        }
        
        # Filter out None values and convert booleans to strings (Redis requirements)
        metadata = {
            k: str(v) if isinstance(v, bool) else v 
            for k, v in metadata.items() 
            if v is not None
        }
        
        #add metadata
        metadata_key = f"{self.task_metadata_prefix}{task_id}"
        self.redis.hset(metadata_key, mapping=metadata)
        self.redis.expire(metadata_key, 86400)  # Expire in 24 hours
        
        # Add to active tasks set
        self.redis.sadd(self.active_tasks_key, task_id)
        self.redis.expire(self.active_tasks_key, 86400)
        
        return task_id
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status and progress"""
        try:
            # Get RQ job
            job = Job.fetch(task_id, connection=self.redis)
            
            # Get metadata
            metadata_key = f"{self.task_metadata_prefix}{task_id}"
            metadata = self.redis.hgetall(metadata_key)
            
            if not metadata:
                return None
            
            # Convert progress to float
            progress = float(metadata.get("progress", 0.0))
            
            # Convert eta_seconds to int if available
            eta_seconds = metadata.get("eta_seconds")
            if eta_seconds and eta_seconds != "None":
                try:
                    eta_seconds = int(float(eta_seconds))
                except (ValueError, TypeError):
                    eta_seconds = None
            else:
                eta_seconds = None
            
            # Get job status
            job_status = job.get_status()
            
            # Map RQ status to our status
            status_mapping = {
                'queued': 'queued',
                'started': 'processing', 
                'finished': 'completed',
                'failed': 'error',
                'deferred': 'queued',
                'canceled': 'error'
            }
            
            status = status_mapping.get(job_status, metadata.get("status", "unknown"))
            
            result = {
                "task_id": task_id,
                "status": status,
                "progress": progress,
                "message": metadata.get("message", ""),
                "created_at": metadata.get("created_at"),
                "eta_seconds": eta_seconds
            }
            
            # Add result if completed
            if job_status == 'finished' and job.result:
                result["result"] = job.result
            
            # Add error if failed
            if job_status == 'failed' and job.exc_info:
                result["error"] = str(job.exc_info)
            
            return result
            
        except NoSuchJobError:
            return None
        except Exception as e:
            print(f"Error getting task status: {e}")
            return None
    
    async def update_task_progress(self, task_id: str, progress: float, message: str, eta_seconds: Optional[int] = None):
        """Update task progress"""
        try:
            metadata_key = f"{self.task_metadata_prefix}{task_id}"
            
            update_data = {
                "progress": str(progress),
                "message": message,
                "updated_at": datetime.now().isoformat()
            }
            
            if eta_seconds is not None:
                update_data["eta_seconds"] = str(eta_seconds)
            
            self.redis.hset(metadata_key, mapping=update_data)
            
        except Exception as e:
            print(f"Error updating task progress: {e}")
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        try:
            job = Job.fetch(task_id, connection=self.redis)
            job.cancel()
            
            # Remove from active tasks
            self.redis.srem(self.active_tasks_key, task_id)
            
            # Update metadata
            metadata_key = f"{self.task_metadata_prefix}{task_id}"
            self.redis.hset(metadata_key, mapping={
                "status": "canceled",
                "message": "Task canceled by user",
                "updated_at": datetime.now().isoformat()
            })
            
            return True
            
        except NoSuchJobError:
            return False
        except Exception as e:
            print(f"Error canceling task: {e}")
            return False
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Clean up old task data"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            # Get all task metadata keys
            pattern = f"{self.task_metadata_prefix}*"
            keys = self.redis.keys(pattern)
            
            for key in keys:
                task_data = self.redis.hgetall(key)
                created_at_str = task_data.get("created_at")
                
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                        if created_at < cutoff_time:
                            # Extract task_id from key
                            task_id = key.replace(self.task_metadata_prefix, "")
                            
                            # Remove from active tasks
                            self.redis.srem(self.active_tasks_key, task_id)
                            
                            # Delete metadata
                            self.redis.delete(key)
                            
                    except ValueError:
                        continue
            
        except Exception as e:
            print(f"Error cleaning up old tasks: {e}")

# Global instance
task_manager = None

def get_task_manager():
    """Get global task manager instance"""
    global task_manager
    if task_manager is None:
        task_manager = RQTaskManager()
    return task_manager