from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any
import psutil
import torch
from rq import Queue, Worker
from ..services.resource_manager import ResourceManager
from ..config import settings
from ..utils.logger import get_logger
from ..utils.redis_client import get_redis_client

router = APIRouter(prefix="/api/v1/system", tags=["system"])
logger = get_logger("system")

@router.get("/health")
async def health_check():
    """Health check endpoint with worker status"""
    try:
        # Check Redis connection
        redis_client = get_redis_client()
        redis_client.ping()
        
        # Check RQ workers
        queue = Queue(settings.task_queue, connection=redis_client)
        workers = Worker.all(connection=redis_client)
        active_workers = [w for w in workers if w.state == 'busy' or w.state == 'idle']
        
        return {
            "status": "healthy",
            "workers": {
                "total": len(workers),
                "active": len(active_workers),
                "max_configured": settings.max_workers
            },
            "queue": {
                "pending_jobs": len(queue),
                "queue_name": settings.task_queue
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@router.get("/stats")
async def get_system_stats():
    """Get detailed system and worker statistics"""
    try:
        # Redis connection
        redis_client = get_redis_client()
        
        # Worker information
        queue = Queue(settings.task_queue, connection=redis_client)
        workers = Worker.all(connection=redis_client)
        
        worker_stats = []
        for worker in workers:
            worker_info = {
                "name": worker.name,
                "state": worker.state,
                "current_job": worker.get_current_job_id(),
                "last_heartbeat": worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
            }
            # birth_date attribute was removed in newer RQ versions
            if hasattr(worker, 'birth_date'):
                worker_info["birth"] = worker.birth_date.isoformat()
            elif hasattr(worker, 'birth'):
                worker_info["birth"] = worker.birth.isoformat()
            worker_stats.append(worker_info)
        
        # Queue statistics
        queue_stats = {
            "pending_jobs": len(queue),
            "failed_jobs": len(queue.failed_job_registry),
            "started_jobs": len(queue.started_job_registry),
            "finished_jobs": len(queue.finished_job_registry)
        }
        
        # System resources
        memory = psutil.virtual_memory()
        system_stats = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": memory.percent,
            "memory_available_gb": memory.available / (1024**3),
            "memory_total_gb": memory.total / (1024**3)
        }
        
        # GPU information
        gpu_stats = {}
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                memory_allocated = torch.cuda.memory_allocated(i)
                memory_total = props.total_memory
                
                gpu_stats[f"gpu_{i}"] = {
                    "name": props.name,
                    "memory_used_gb": memory_allocated / (1024**3),
                    "memory_total_gb": memory_total / (1024**3),
                    "memory_percent": (memory_allocated / memory_total) * 100
                }
        
        return {
            "workers": {
                "total": len(workers),
                "active": len([w for w in workers if w.state in ['busy', 'idle']]),
                "max_configured": settings.max_workers,
                "details": worker_stats
            },
            "queue": queue_stats,
            "system": system_stats,
            "gpu": gpu_stats,
            "configuration": {
                "max_workers": settings.max_workers,
                "worker_concurrency": settings.worker_concurrency,
                "task_timeout": settings.task_timeout
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system stats: {str(e)}"
        )

@router.get("/resources")
async def get_resource_usage():
    """Get current resource usage and worker status"""
    try:
        resource_manager = ResourceManager()
        
        # System resources
        memory = psutil.virtual_memory()
        system_resources = {
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "percent": memory.percent
            },
            "cpu": {
                "count": psutil.cpu_count(),
                "usage": psutil.cpu_percent(interval=1)
            }
        }
        
        # GPU resources
        gpu_resources = {}
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            for i in range(gpu_count):
                props = torch.cuda.get_device_properties(i)
                memory_allocated = torch.cuda.memory_allocated(i)
                memory_cached = torch.cuda.memory_reserved(i)
                memory_total = props.total_memory
                
                gpu_resources[f"gpu_{i}"] = {
                    "name": props.name,
                    "total_memory": memory_total,
                    "allocated_memory": memory_allocated,
                    "cached_memory": memory_cached,
                    "free_memory": memory_total - memory_cached,
                    "utilization_percent": (memory_cached / memory_total) * 100
                }
        
        # Worker status
        worker_status = resource_manager.get_all_workers()
        
        return {
            "system": system_resources,
            "gpu": gpu_resources,
            "workers": worker_status,
            "resource_limits": {
                "max_vram_gb": resource_manager.max_vram_gb,
                "max_ram_gb": resource_manager.max_ram_gb
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get resource usage: {str(e)}"
        )

@router.get("/models")
async def get_model_availability():
    """Get available models and their resource requirements"""
    try:
        resource_manager = ResourceManager()
        
        model_info = {}
        for model_spec in resource_manager.model_specs.values():
            can_load = resource_manager.can_load_model(model_spec.name)
            model_info[model_spec.name] = {
                "vram_mb": model_spec.vram_mb,
                "ram_mb": model_spec.ram_mb,
                "available": can_load
            }
        
        # Get best available model
        best_model = resource_manager.suggest_best_model()
        
        return {
            "models": model_info,
            "best_available": best_model
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model availability: {str(e)}"
        )

@router.post("/workers/cleanup")
async def cleanup_stale_workers():
    """Clean up stale worker registrations"""
    try:
        resource_manager = ResourceManager()
        cleaned_count = resource_manager.cleanup_stale_workers()
        
        return {
            "message": f"Cleaned up {cleaned_count} stale workers",
            "cleaned_count": cleaned_count
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup workers: {str(e)}"
        )