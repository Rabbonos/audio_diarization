from fastapi import FastAPI
import uvicorn
import os
from datetime import datetime
from contextlib import asynccontextmanager
from .config import settings
from .routers import transcription, system
from .middleware.rate_limit import RateLimitMiddleware, TranscriptionRateLimitMiddleware
from .services.storage_service import storage_service
from .services.database_service import db_service
from .utils.logger import get_logger
from .utils.redis_client import get_redis_client

# Initialize logger
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    logger.info("🚀 Starting Audio Diarization Service...")
    
    # Create upload directory on startup (fallback for local storage)
    os.makedirs(settings.upload_dir, exist_ok=True)
    logger.info(f"Upload directory created: {settings.upload_dir}")
    
    # Initialize database
    try:
        # Database service is already initialized in its constructor
        logger.info("✅ Database service initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        raise
    
    # Initialize MinIO if enabled
    if settings.use_minio:
        try:
            # Force initialization of storage service
            storage_service._init_minio()
            if storage_service.use_minio:
                logger.info("✅ MinIO storage initialized successfully")
            else:
                logger.warning("⚠️ MinIO initialization failed, using local storage")
        except Exception as e:
            logger.warning(f"⚠️ MinIO initialization error: {e}, falling back to local storage")
    
    logger.info("✅ Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down Audio Diarization Service...")


app = FastAPI(
    title=settings.api_title,
    description="MVP for audio transcription and diarization using Whisper and pyannote",
    version=settings.api_version,
    lifespan=lifespan
)

# Add rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    calls=60,  # 60 requests per minute for general API
    period=60
)
app.add_middleware(
    TranscriptionRateLimitMiddleware,
    calls=10,  # 10 transcription requests per minute
    period=60
)

# Include routers (they already have /api/v1 prefix)
app.include_router(transcription.router)
app.include_router(system.router)

@app.get("/")
async def root():
    return {"message": "Audio Diarization Service MVP", "status": "running"}

@app.get("/health")
async def health_check():
    try:
        # Test Redis connection
        redis_client = get_redis_client()
        redis_client.ping()
        
        return {
            "status": "healthy", 
            "timestamp": datetime.now().isoformat(),
            "services": {
                "redis": "connected",
                "api": "running"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
