import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Set

class Settings(BaseSettings):
    # Configuration using Pydantic v2 model_config
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra environment variables not defined in Settings
    )
    
    # API Configuration
    api_title: str = "Audio Diarization Service"
    api_version: str = "1.0.0"
    api_key: str = "mvp-api-key-123"
    
    # HuggingFace
    hf_token: str = "your_huggingface_token_here"
    
    # Redis Configuration
    redis_url: str = "redis://redis:6379/0"
    
    # Database Configuration
    database_url: str = "postgresql://user:password@postgres:5432/audio_db"
    
    # File Configuration
    upload_dir: str = "/tmp/audio_processing"  # Temporary processing directory (even with S3)
    log_dir: str = "logs"  # Default log directory (relative to project root)
    model_cache_dir: str = "/models"  # Shared models directory (readonly in workers)
    max_file_size: int = 500 * 1024 * 1024  # 500MB
    max_duration_hours: int = 8  # Maximum 8 hours
    max_duration_seconds: int = 8 * 3600  # 8 hours in seconds
    
    # MinIO S3 Configuration
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_name: str = "audio-files"
    minio_secure: bool = False  # Set to True for HTTPS
    use_minio: bool = True  # Enable MinIO storage
    
    # Supported formats - including wma and wmv
    allowed_audio_extensions: Set[str] = {
        '.mp3', '.m4a', '.aac', '.wav', '.mpeg', '.ogg', 
        '.opus', '.flac', '.mp4', '.mov', '.avi', '.wma', '.wmv'
    }
    
    # Worker Configuration (Controls parallel processing capacity)
    max_workers: int = 3  # Number of worker processes (each processes 1 task at a time)
    task_timeout: int = 3600  # 1 hour timeout
    task_queue: str = "audio_tasks"  # RQ queue name
    
    # Note: RQ workers are single-threaded by design. Each worker process
    # handles exactly 1 task at a time. To increase concurrency, scale the
    # number of worker processes (MAX_WORKERS), not tasks per worker.
    
    # Resource Management (for monitoring)
    max_vram_gb: int = 16  # Maximum VRAM available
    max_ram_gb: int = 32   # Maximum RAM available
    
    # Whisper settings
    whisper_model: str = "medium"  # MVP model for balance of speed/accuracy

settings = Settings()