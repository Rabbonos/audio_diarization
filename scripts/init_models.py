#!/usr/bin/env python3
"""
Model Initialization Script
Pre-downloads Whisper models to shared volume for fast worker startup
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import whisper
import torch
from src.config import settings

# Available Whisper models (ordered by size)
WHISPER_MODELS = [
    "tiny",      # ~75 MB
    "base",      # ~150 MB
    "small",     # ~500 MB
    "medium",    # ~1.5 GB
    "large",     # ~3 GB
    "large-v2",  # ~3 GB
    "large-v3",  # ~3 GB
]

def download_model(model_name: str, cache_dir: Path) -> bool:
    """Download a single model to cache directory"""
    try:
        print(f"\n{'='*60}")
        print(f"Downloading Whisper model: {model_name}")
        print(f"Cache directory: {cache_dir}")
        print(f"{'='*60}")
        
        # Download model
        model = whisper.load_model(
            model_name,
            device="cuda" if torch.cuda.is_available() else "cpu",
            download_root=str(cache_dir)
        )
        
        print(f"✓ Successfully downloaded model: {model_name}")
        
        # Free memory
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to download model {model_name}: {e}")
        return False

def main():
    """Main initialization function"""
    print("=" * 60)
    print("Whisper Model Initialization")
    print("=" * 60)
    
    # Get cache directory
    cache_dir = Path(settings.model_cache_dir)
    print(f"\nModel cache directory: {cache_dir}")
    
    # Ensure cache directory exists and is writable
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        print(f"✓ Cache directory ready")
    except Exception as e:
        print(f"✗ Failed to create cache directory: {e}")
        sys.exit(1)
    
    # Check GPU availability
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        print(f"✓ GPU available: {gpu_name}")
    else:
        print("⚠ No GPU available - models will download on CPU")
    
    # Get target model from environment
    models_env = os.getenv("WHISPER_MODELS_TO_DOWNLOAD", "").strip()
    
    # Determine which models to download
    models_to_download = []
    
    if models_env:
        if models_env.lower() == "all":
            # Download all models
            models_to_download = WHISPER_MODELS
            print(f"WHISPER_MODELS_TO_DOWNLOAD=all - Will download ALL models")
        else:
            # Parse comma-separated list
            requested_models = [m.strip() for m in models_env.split(",")]
            models_to_download = [m for m in requested_models if m in WHISPER_MODELS]
            
            invalid_models = [m for m in requested_models if m not in WHISPER_MODELS]
            if invalid_models:
                print(f"⚠ Invalid models ignored: {', '.join(invalid_models)}")
            
            print(f"WHISPER_MODELS_TO_DOWNLOAD={models_env}")
            print(f"Will download: {', '.join(models_to_download)}")
    else:
        # Fallback: download only the WHISPER_MODEL
        target_model = os.getenv("WHISPER_MODEL", settings.whisper_model)
        if target_model in WHISPER_MODELS:
            models_to_download = [target_model]
            print(f"No WHISPER_MODELS_TO_DOWNLOAD set, using WHISPER_MODEL={target_model}")
        else:
            models_to_download = ["base"]
            print(f"⚠ Invalid WHISPER_MODEL, defaulting to 'base'")
    
    if not models_to_download:
        print("✗ No valid models to download!")
        sys.exit(1)
    
    # Download models
    print(f"\n{'='*60}")
    print(f"Starting model downloads...")
    print(f"{'='*60}")
    
    success_count = 0
    failed_models = []
    
    for model_name in models_to_download:
        if download_model(model_name, cache_dir):
            success_count += 1
        else:
            failed_models.append(model_name)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Model Initialization Complete")
    print(f"{'='*60}")
    print(f"✓ Successfully downloaded: {success_count}/{len(models_to_download)} models")
    
    if failed_models:
        print(f"✗ Failed models: {', '.join(failed_models)}")
        sys.exit(1)
    
    # List cached files
    print(f"\n{'='*60}")
    print(f"Cached files in {cache_dir}:")
    print(f"{'='*60}")
    
    total_size = 0
    for file_path in sorted(cache_dir.rglob("*")):
        if file_path.is_file():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            total_size += size_mb
            print(f"  {file_path.name}: {size_mb:.2f} MB")
    
    print(f"\nTotal cache size: {total_size:.2f} MB ({total_size/1024:.2f} GB)")
    print(f"\n✓ Model initialization successful!")
    print(f"Workers can now quickly load models from: {cache_dir}")

if __name__ == "__main__":
    main()
