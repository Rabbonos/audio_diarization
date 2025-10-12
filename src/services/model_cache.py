"""
Whisper Model Cache Manager
Efficiently caches Whisper models with resource management
"""
import os
import pickle
import hashlib
import threading
from pathlib import Path
from typing import Dict, Any, Optional
import whisper
import torch
from ..config import settings

class WhisperModelCache:
    """
    Smart caching system for Whisper models with resource management
    - Downloads models once to disk
    - Integrates with ResourceManager for VRAM/RAM limits
    - Thread-safe for multi-worker environments
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, 'initialized'):
            return
        
        # Use shared model cache directory (readonly in workers)
        self.cache_dir = Path(settings.model_cache_dir)
        
        # Create cache directory only if writable (for init container)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.is_writable = True
        except (PermissionError, OSError):
            # Directory is readonly - this is expected in worker containers
            self.is_writable = False
            print(f"Model cache directory is readonly: {self.cache_dir}")
        
        # In-memory cache: {model_name: model_on_cpu}
        self.cpu_cache: Dict[str, Any] = {}
        self.cache_lock = threading.Lock()
        
        # Device management
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Model metadata cache
        self.model_metadata = self._load_metadata()
        
        # Resource manager will be injected
        self.resource_manager = None
        
        self.initialized = True
    
    def set_resource_manager(self, resource_manager):
        """Set the resource manager (dependency injection)"""
        self.resource_manager = resource_manager
    
    def _get_cache_path(self, model_name: str) -> Path:
        """Get cache file path for a model"""
        # Create a safe filename
        safe_name = hashlib.md5(model_name.encode()).hexdigest()
        return self.cache_dir / f"whisper_{model_name}_{safe_name}.pkl"
    
    def _get_metadata_path(self) -> Path:
        """Get metadata cache file path"""
        return self.cache_dir / "model_metadata.json"
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load model metadata from cache"""
        metadata_path = self._get_metadata_path()
        if metadata_path.exists():
            try:
                import json
                with open(metadata_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load model metadata from {metadata_path}: {e}")
        return {}
    
    def _save_metadata(self):
        """Save model metadata to cache"""
        try:
            import json
            with open(self._get_metadata_path(), 'w') as f:
                json.dump(self.model_metadata, f)
        except Exception as e:
            print(f"Warning: Failed to save model metadata: {e}")
    
    def _download_and_cache_model(self, model_name: str) -> Any:
        """Download model and save to disk cache"""
        cache_path = self._get_cache_path(model_name)
        
        # Check if already cached (by another process/init container)
        if cache_path.exists():
            print(f"Model already cached at: {cache_path}")
            try:
                with open(cache_path, 'rb') as f:
                    model = pickle.load(f)
                return model
            except Exception as e:
                print(f"Failed to load cached model, will re-download: {e}")
        
        # Check if cache is writable
        if not self.is_writable:
            raise Exception(
                f"Model {model_name} not found in cache and cache directory is readonly. "
                f"Please run model initialization first."
            )
        
        print(f"Downloading and caching Whisper model: {model_name}")
        
        # Download model to CPU first (saves VRAM)
        model = whisper.load_model(model_name, device="cpu", download_root=str(self.cache_dir))
        
        # Cache to disk
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(model, f)
            
            # Update metadata
            self.model_metadata[model_name] = {
                "cached_at": str(torch.utils.data.get_worker_info() or "main"),
                "cache_path": str(cache_path),
                "model_size": cache_path.stat().st_size if cache_path.exists() else 0
            }
            self._save_metadata()
            
            print(f"Model {model_name} cached to disk: {cache_path}")
            
        except Exception as e:
            print(f"Warning: Failed to cache model to disk: {e}")
        
        return model
    
    def _load_from_disk_cache(self, model_name: str) -> Optional[Any]:
        """Load model from disk cache"""
        cache_path = self._get_cache_path(model_name)
        
        if not cache_path.exists():
            return None
        
        try:
            print(f"Loading cached model from disk: {model_name}")
            with open(cache_path, 'rb') as f:
                model = pickle.load(f)
            return model
        except Exception as e:
            print(f"Warning: Failed to load cached model: {e}")
            # Remove corrupted cache file
            try:
                cache_path.unlink()
            except:
                pass
            return None
    
    def get_model(self, model_name: str, for_gpu: bool = True) -> Any:
        """
        Get Whisper model with smart caching and resource management
        Returns model on CPU - call move_to_device() when ready to process
        """
        # Check resource limits first if resource manager is available
        if self.resource_manager:
            can_load, reason = self.resource_manager.can_load_model(model_name, for_gpu)
            if not can_load:
                # Suggest alternative model
                suggested_model, suggestion_reason = self.resource_manager.suggest_best_model(model_name)
                if suggested_model != model_name:
                    print(f"Switching from {model_name} to {suggested_model}: {suggestion_reason}")
                    model_name = suggested_model
                else:
                    raise Exception(f"Cannot load model {model_name}: {reason}")
        
        with self.cache_lock:
            # Check CPU memory cache first
            if model_name in self.cpu_cache:
                print(f"Using cached model from memory: {model_name}")
                # Reserve resources if using resource manager
                if self.resource_manager:
                    if not self.resource_manager.reserve_model(model_name, for_gpu):
                        raise Exception(f"Failed to reserve resources for {model_name}")
                return self.cpu_cache[model_name]
            
            # Check if we can load the model into memory
            if self.resource_manager:
                can_load, reason = self.resource_manager.can_load_model(model_name, False)  # RAM check
                if not can_load:
                    # Try to free some memory
                    self._free_memory_if_needed()
                    # Check again
                    can_load, reason = self.resource_manager.can_load_model(model_name, False)
                    if not can_load:
                        raise Exception(f"Cannot load model {model_name} into memory: {reason}")
            
            # Try loading from disk cache
            model = self._load_from_disk_cache(model_name)
            
            # If not cached, download and cache
            if model is None:
                model = self._download_and_cache_model(model_name)
            
            # Store in CPU memory cache
            self.cpu_cache[model_name] = model
            
            # Reserve resources
            if self.resource_manager:
                if not self.resource_manager.reserve_model(model_name, for_gpu):
                    # Remove from cache if we can't reserve
                    del self.cpu_cache[model_name]
                    raise Exception(f"Failed to reserve resources for {model_name}")
            
            print(f"Model {model_name} ready on CPU")
            return model
    
    def _free_memory_if_needed(self):
        """Free some memory by removing cached models"""
        if len(self.cpu_cache) > 1:  # Keep at least one model
            # Remove the oldest cached model (simple LRU)
            oldest_model = next(iter(self.cpu_cache))
            print(f"Freeing memory by removing cached model: {oldest_model}")
            if self.resource_manager:
                self.resource_manager.release_model(oldest_model)
            del self.cpu_cache[oldest_model]
    
    def move_to_device(self, model: Any, device: Optional[str] = None) -> Any:
        """Move model to specified device (GPU/CPU) for processing"""
        target_device = device or self.device
        
        if target_device == "cuda" and torch.cuda.is_available():
            print(f"Moving model to GPU for processing")
            return model.to(target_device)
        else:
            print(f"Using model on CPU")
            return model.to("cpu")
    
    def release_gpu_memory(self, model: Any, model_name: str = None) -> Any:
        """Move model back to CPU to free GPU memory"""
        if torch.cuda.is_available():
            model_cpu = model.cpu()
            torch.cuda.empty_cache()
            print("Released GPU memory, model moved to CPU")
            
            # Release GPU resources in resource manager
            if self.resource_manager and model_name:
                self.resource_manager.release_model(model_name)
                # Re-reserve for CPU only
                self.resource_manager.reserve_model(model_name, on_gpu=False)
            
            return model_cpu
        return model
    
    def release_model(self, model_name: str):
        """Completely release a model and its resources"""
        with self.cache_lock:
            if model_name in self.cpu_cache:
                del self.cpu_cache[model_name]
                print(f"Released model from cache: {model_name}")
                
                # Release resources
                if self.resource_manager:
                    self.resource_manager.release_model(model_name)
    
    def clear_memory_cache(self):
        """Clear CPU memory cache (keeps disk cache)"""
        with self.cache_lock:
            self.cpu_cache.clear()
            print("Cleared model memory cache")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about cached models"""
        info = {
            "memory_cached_models": list(self.cpu_cache.keys()),
            "disk_cached_models": list(self.model_metadata.keys()),
            "cache_directory": str(self.cache_dir),
            "total_cache_size_mb": 0
        }
        
        # Calculate total cache size
        total_size = 0
        for cache_path in self.cache_dir.glob("whisper_*.pkl"):
            if cache_path.exists():
                total_size += cache_path.stat().st_size
        
        info["total_cache_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        return info

# Global cache instance
model_cache = WhisperModelCache()