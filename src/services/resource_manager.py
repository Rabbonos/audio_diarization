"""
Resource Manager for Multi-Worker Model Management
Handles VRAM/RAM limits across RQ workers with Redis coordination
"""
import os
import json
import time
import psutil
import threading
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
import redis
import torch
from ..config import settings

@dataclass
class ModelSpec:
    """Model specifications for resource calculation"""
    name: str
    vram_mb: int  # VRAM usage when loaded on GPU
    ram_mb: int   # RAM usage when loaded on CPU
    download_mb: int  # Download size

class ModelSize(Enum):
    """Whisper model sizes with actual resource requirements"""
    TINY = ModelSpec("tiny", 200, 100, 39)
    BASE = ModelSpec("base", 300, 150, 74) 
    SMALL = ModelSpec("small", 500, 400, 244)
    MEDIUM = ModelSpec("medium", 1200, 800, 769)
    LARGE = ModelSpec("large", 2500, 1600, 1550)
    LARGE_V2 = ModelSpec("large-v2", 2500, 1600, 1550)
    LARGE_V3 = ModelSpec("large-v3", 2500, 1600, 1550)
    TURBO = ModelSpec("turbo", 1500, 900, 800)

class ResourceManager:
    """
    Manages VRAM/RAM resources across multiple RQ workers
    Uses Redis for coordination between worker processes
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client or redis.from_url(settings.redis_url, decode_responses=True)
        
        # Resource limits (configurable)
        self.max_vram_mb = getattr(settings, 'max_vram_mb', 16000)  # 16GB default
        self.max_ram_mb = getattr(settings, 'max_ram_mb', 8000)     # 8GB default for models
        self.pyannote_vram_mb = 1500  # pyannote pipeline VRAM usage
        
        # Redis keys for coordination
        self.active_models_key = "resource_manager:active_models"
        self.resource_usage_key = "resource_manager:usage"
        self.worker_registry_key = "resource_manager:workers"
        
        # Worker ID
        self.worker_id = f"worker_{os.getpid()}_{int(time.time())}"
        
        # Model specs lookup
        self.model_specs = {spec.value.name: spec.value for spec in ModelSize}
        
        # Lock for critical sections
        self._lock = threading.Lock()
        
        # Register this worker
        self._register_worker()
    
    def _register_worker(self):
        """Register this worker in Redis"""
        worker_data = {
            "pid": os.getpid(),
            "registered_at": time.time(),
            "last_heartbeat": time.time()
        }
        self.redis.hset(self.worker_registry_key, self.worker_id, json.dumps(worker_data))
    
    def _cleanup_stale_workers(self):
        """Remove stale worker registrations"""
        try:
            workers = self.redis.hgetall(self.worker_registry_key)
            current_time = time.time()
            
            for worker_id, data_str in workers.items():
                try:
                    data = json.loads(data_str)
                    # Remove workers that haven't sent heartbeat in 5 minutes
                    if current_time - data.get("last_heartbeat", 0) > 300:
                        self.redis.hdel(self.worker_registry_key, worker_id)
                        # Also clean up their model usage
                        self._release_worker_resources(worker_id)
                except (json.JSONDecodeError, KeyError):
                    # Remove corrupted entries
                    self.redis.hdel(self.worker_registry_key, worker_id)
        except Exception as e:
            print(f"Warning: Failed to cleanup stale workers: {e}")
    
    def _heartbeat(self):
        """Send heartbeat to indicate worker is alive"""
        try:
            worker_data = self.redis.hget(self.worker_registry_key, self.worker_id)
            if worker_data:
                data = json.loads(worker_data)
                data["last_heartbeat"] = time.time()
                self.redis.hset(self.worker_registry_key, self.worker_id, json.dumps(data))
        except Exception as e:
            print(f"Warning: Failed to send heartbeat: {e}")
    
    def _get_current_usage(self) -> Tuple[int, int]:
        """Get current VRAM and RAM usage across all workers"""
        try:
            usage_data = self.redis.get(self.resource_usage_key)
            if usage_data:
                usage = json.loads(usage_data)
                return usage.get("vram_mb", 0), usage.get("ram_mb", 0)
        except Exception:
            pass
        return 0, 0
    
    def _update_usage(self, vram_delta: int, ram_delta: int):
        """Update global resource usage"""
        try:
            with self._lock:
                current_vram, current_ram = self._get_current_usage()
                new_usage = {
                    "vram_mb": max(0, current_vram + vram_delta),
                    "ram_mb": max(0, current_ram + ram_delta),
                    "updated_at": time.time()
                }
                self.redis.set(self.resource_usage_key, json.dumps(new_usage), ex=3600)
        except Exception as e:
            print(f"Warning: Failed to update resource usage: {e}")
    
    def can_load_model(self, model_name: str, on_gpu: bool = True) -> Tuple[bool, str]:
        """
        Check if model can be loaded without exceeding resource limits
        
        Returns:
            (can_load: bool, reason: str)
        """
        self._cleanup_stale_workers()
        self._heartbeat()
        
        if model_name not in self.model_specs:
            return False, f"Unknown model: {model_name}"
        
        model_spec = self.model_specs[model_name]
        current_vram, current_ram = self._get_current_usage()
        
        if on_gpu:
            # Check VRAM limits (including pyannote)
            required_vram = model_spec.vram_mb + self.pyannote_vram_mb
            if current_vram + required_vram > self.max_vram_mb:
                return False, f"VRAM limit exceeded: {current_vram + required_vram}MB > {self.max_vram_mb}MB"
        
        # Always check RAM (models cached on CPU)
        required_ram = model_spec.ram_mb
        if current_ram + required_ram > self.max_ram_mb:
            return False, f"RAM limit exceeded: {current_ram + required_ram}MB > {self.max_ram_mb}MB"
        
        # Check system RAM
        system_ram = psutil.virtual_memory()
        if system_ram.percent > 85:  # If system RAM > 85%, don't load more models
            return False, f"System RAM too high: {system_ram.percent}%"
        
        return True, "OK"
    
    def reserve_model(self, model_name: str, on_gpu: bool = True) -> bool:
        """
        Reserve resources for a model
        
        Returns:
            success: bool
        """
        can_load, reason = self.can_load_model(model_name, on_gpu)
        if not can_load:
            print(f"Cannot reserve model {model_name}: {reason}")
            return False
        
        model_spec = self.model_specs[model_name]
        
        # Reserve resources
        vram_usage = model_spec.vram_mb + self.pyannote_vram_mb if on_gpu else 0
        ram_usage = model_spec.ram_mb
        
        self._update_usage(vram_usage, ram_usage)
        
        # Track worker's model usage
        worker_models_key = f"worker_models:{self.worker_id}"
        model_data = {
            "model_name": model_name,
            "on_gpu": on_gpu,
            "vram_mb": vram_usage,
            "ram_mb": ram_usage,
            "reserved_at": time.time()
        }
        self.redis.hset(worker_models_key, model_name, json.dumps(model_data))
        self.redis.expire(worker_models_key, 3600)  # Expire in 1 hour
        
        print(f"Reserved {model_name}: VRAM={vram_usage}MB, RAM={ram_usage}MB")
        return True
    
    def release_model(self, model_name: str):
        """Release resources for a model"""
        try:
            worker_models_key = f"worker_models:{self.worker_id}"
            model_data_str = self.redis.hget(worker_models_key, model_name)
            
            if model_data_str:
                model_data = json.loads(model_data_str)
                vram_usage = model_data.get("vram_mb", 0)
                ram_usage = model_data.get("ram_mb", 0)
                
                # Release resources
                self._update_usage(-vram_usage, -ram_usage)
                
                # Remove from worker's models
                self.redis.hdel(worker_models_key, model_name)
                
                print(f"Released {model_name}: VRAM={vram_usage}MB, RAM={ram_usage}MB")
            
        except Exception as e:
            print(f"Warning: Failed to release model resources: {e}")
    
    def _release_worker_resources(self, worker_id: str):
        """Release all resources for a worker"""
        try:
            worker_models_key = f"worker_models:{worker_id}"
            models = self.redis.hgetall(worker_models_key)
            
            total_vram = 0
            total_ram = 0
            
            for model_name, data_str in models.items():
                try:
                    data = json.loads(data_str)
                    total_vram += data.get("vram_mb", 0)
                    total_ram += data.get("ram_mb", 0)
                except:
                    continue
            
            if total_vram > 0 or total_ram > 0:
                self._update_usage(-total_vram, -total_ram)
                print(f"Released resources for dead worker {worker_id}: VRAM={total_vram}MB, RAM={total_ram}MB")
            
            # Clean up worker's model tracking
            self.redis.delete(worker_models_key)
            
        except Exception as e:
            print(f"Warning: Failed to release worker resources: {e}")
    
    def get_resource_status(self) -> Dict[str, Any]:
        """Get current resource usage status"""
        self._cleanup_stale_workers()
        
        current_vram, current_ram = self._get_current_usage()
        system_memory = psutil.virtual_memory()
        
        # Get GPU memory if available
        gpu_memory = {}
        if torch.cuda.is_available():
            gpu_memory = {
                "total_mb": torch.cuda.get_device_properties(0).total_memory // (1024*1024),
                "allocated_mb": torch.cuda.memory_allocated() // (1024*1024),
                "cached_mb": torch.cuda.memory_reserved() // (1024*1024)
            }
        
        # Get active workers
        workers = self.redis.hgetall(self.worker_registry_key)
        active_workers = []
        for worker_id, data_str in workers.items():
            try:
                data = json.loads(data_str)
                active_workers.append({
                    "worker_id": worker_id,
                    "pid": data.get("pid"),
                    "last_heartbeat": data.get("last_heartbeat")
                })
            except:
                continue
        
        return {
            "limits": {
                "max_vram_mb": self.max_vram_mb,
                "max_ram_mb": self.max_ram_mb
            },
            "usage": {
                "vram_mb": current_vram,
                "ram_mb": current_ram,
                "vram_percent": round((current_vram / self.max_vram_mb) * 100, 1),
                "ram_percent": round((current_ram / self.max_ram_mb) * 100, 1)
            },
            "system": {
                "total_ram_mb": round(system_memory.total / (1024*1024)),
                "used_ram_percent": system_memory.percent,
                "available_ram_mb": round(system_memory.available / (1024*1024))
            },
            "gpu": gpu_memory,
            "active_workers": len(active_workers),
            "workers": active_workers
        }
    
    def suggest_best_model(self, requested_model: str) -> Tuple[str, str]:
        """
        Suggest the best available model given resource constraints
        
        Returns:
            (suggested_model: str, reason: str)
        """
        # Try requested model first
        can_load, reason = self.can_load_model(requested_model, on_gpu=True)
        if can_load:
            return requested_model, "Requested model available"
        
        # Try smaller models in order of preference
        model_hierarchy = ["large-v3", "large-v2", "large", "turbo", "medium", "small", "base", "tiny"]
        
        for model_name in model_hierarchy:
            if model_name == requested_model:
                continue  # Already tried
            can_load, _ = self.can_load_model(model_name, on_gpu=True)
            if can_load:
                return model_name, f"Suggested smaller model due to: {reason}"
        
        return "tiny", f"Only tiny model fits due to: {reason}"
    
    def cleanup(self):
        """Cleanup worker resources on shutdown"""
        try:
            # Release all models for this worker
            worker_models_key = f"worker_models:{self.worker_id}"
            models = self.redis.hgetall(worker_models_key)
            
            for model_name in models.keys():
                self.release_model(model_name)
            
            # Unregister worker
            self.redis.hdel(self.worker_registry_key, self.worker_id)
            self.redis.delete(worker_models_key)
            
        except Exception as e:
            print(f"Warning: Failed to cleanup worker resources: {e}")

# Global resource manager instance
resource_manager = None

def get_resource_manager() -> ResourceManager:
    """Get global resource manager instance"""
    global resource_manager
    if resource_manager is None:
        resource_manager = ResourceManager()
    return resource_manager