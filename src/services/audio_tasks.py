"""
RQ task functions for audio processing - FULLY SYNCHRONOUS
No async/await at all - pure synchronous code for RQ workers
"""
import os
from datetime import datetime, timezone
from typing import Dict, Any
from .audio_processor import AudioProcessor
from .result_service import result_service
from .storage_service import storage_service

try:
    # Try relative imports first (for FastAPI app)
    from ..config import settings
    from ..utils.logger import get_logger
    from ..utils.redis_client import get_redis_client
except ImportError:
    # Fall back to absolute imports (for RQ worker script)
    from config import settings
    from utils.logger import get_logger
    from utils.redis_client import get_redis_client

logger = get_logger("audio_tasks")


def update_progress(task_id: str, progress: float, message: str, status: str = "processing") -> None:
    """Sync progress update - always includes status to prevent data loss"""
    try:
        redis_client = get_redis_client()
        task_key = f"task:{task_id}"
        
        # Use pipeline to ensure atomicity
        pipe = redis_client.pipeline()
        pipe.hset(task_key, mapping={
            "status": status,
            "progress": int(progress),
            "message": message,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        pipe.expire(task_key, 86400)  # 24 hours
        pipe.execute()
        
        print(f"✅ Redis UPDATE: task_id={task_id}, status={status}, progress={progress}%, msg={message}")
        logger.info(f"Progress update: {task_id} -> {status} ({progress}%): {message}")
        
    except Exception as e:
        print(f"❌ Redis UPDATE FAILED: task_id={task_id}, error={e}")
        logger.error(f"Progress update failed for {task_id}: {e}")


def process_transcription_task(
    file_path: str,
    storage_path: str = None,
    language: str = "auto",
    model: str = "medium",
    format_type: str = "json",
    diarization: bool = True,
    original_filename: str = None,
    api_token: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    RQ task - FULLY SYNCHRONOUS, no async/await
    Just plain Python code that RQ workers can execute directly
    """
    from rq import get_current_job
    import whisper
    import torch
    
    job = get_current_job()
    task_id = job.id
    start_time = datetime.now(timezone.utc)
    
    print("=" * 80)
    print(f"🚀 WORKER STARTED: task_id={task_id}")
    print(f"   file_path={file_path}")
    print(f"   storage_path={storage_path}")
    print(f"   model={model}, language={language}")
    print("=" * 80)
    
    def progress(percent: float, msg: str):
        print(f"   📊 Progress: {percent}% - {msg}")
        update_progress(task_id, percent, msg, status="processing")
    
    try:
        print("🔄 Setting initial progress...")
        progress(0, "Starting...")
        
        # Download file if needed - using MinIO sync client
        local_file_path = file_path
        if storage_path:
            progress(5, "Downloading file...")
            
            # Direct synchronous MinIO download
            if storage_service.use_minio and storage_service.minio_client:
                import tempfile
                
                # Extract object key from S3 URI if needed
                # storage_path could be: "s3://bucket/uploads/file.wav" or just "uploads/file.wav"
                object_key = storage_path
                if storage_path.startswith("s3://"):
                    # Remove "s3://bucket-name/" prefix to get just the object key
                    parts = storage_path.replace("s3://", "").split("/", 1)
                    if len(parts) > 1:
                        object_key = parts[1]  # Get everything after bucket name
                
                local_file_path = os.path.join(tempfile.gettempdir(), os.path.basename(object_key))
                storage_service.minio_client.fget_object(
                    settings.minio_bucket_name,
                    object_key,  # Use extracted object key, not full URI
                    local_file_path
                )
            else:
                # Local filesystem - just use the path
                local_file_path = os.path.join(storage_service.local_upload_dir, storage_path)
            
            logger.info(f"Downloaded: {storage_path}")
        
        # Check file exists
        if not os.path.exists(local_file_path):
            raise Exception(f"File not found: {local_file_path}")
        
        progress(10, "Loading model...")
        
        # Load Whisper model from shared volume cache
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Use MODEL_CACHE_DIR from environment (mounted shared volume)
        model_cache_dir = os.getenv("MODEL_CACHE_DIR", "/models")
        
        logger.info(f"Loading model '{model}' from cache: {model_cache_dir}")
        whisper_model = whisper.load_model(
            model, 
            device=device,
            download_root=model_cache_dir  # Use pre-downloaded models from shared volume
        )
        
        progress(20, "Transcribing audio...")
        
        # Transcribe synchronously
        result = whisper_model.transcribe(
            local_file_path,
            language=None if language == "auto" else language,
            verbose=False
        )
        
        progress(90, "Processing results...")
        
        # Format result
        formatted_result = {
            "text": result.get("text", ""),
            "segments": result.get("segments", []),
            "language": result.get("language", "unknown")
        }
        
        progress(95, "Saving results...")
        
        # Save to database synchronously
        end_time = datetime.now(timezone.utc)
        metadata = {
            'started_at': start_time,
            'completed_at': end_time,
            'processing_time_seconds': (end_time - start_time).total_seconds(),
            'original_filename': original_filename
        }
        
        # Direct database insert (synchronous)
        try:
            try:
                from ..models import TranscriptionResult
            except ImportError:
                from models import TranscriptionResult
            
            # Import db_service at module level to ensure same instance
            from services.database_service import db_service
            
            # Re-initialize if needed (idempotent)
            if not db_service._initialized:
                print("⚠️  Database not initialized in task, initializing now...")
                db_service.initialize()
            
            print(f"💾 Saving to database: task_id={task_id}")
            
            db_result = TranscriptionResult(
                task_id=task_id,
                api_token=api_token or "unknown",
                transcription_text=formatted_result["text"],
                formatted_result=formatted_result,  # Correct column name
                status="completed",
                processing_time_seconds=metadata['processing_time_seconds'],
                original_filename=original_filename,
                detected_language=formatted_result.get("language", "unknown"),
                word_count=len(formatted_result["text"].split()) if formatted_result["text"] else 0,
                started_at=start_time,
                completed_at=end_time
            )
            
            with db_service.get_session() as session:
                session.add(db_result)
                session.commit()
                print(f"✅ Database save successful")
                logger.info(f"✅ Saved transcription result to database")
                
        except Exception as db_error:
            print(f"❌ Database save failed: {db_error}")
            import traceback
            traceback.print_exc()
            logger.error(f"Failed to save to database: {db_error}")
        
        # Update Redis cache with JSON
        import json
        redis_client = get_redis_client()
        
        print(f"💾 Caching result in Redis: transcription_result:{task_id}")
        redis_client.setex(
            f"transcription_result:{task_id}",
            3600 * 24,  # 24 hours
            json.dumps(formatted_result)  # Store as JSON string, not Python str
        )
        
        # Update task status to completed
        print(f"✅ Setting final status to COMPLETED for task {task_id}")
        redis_client.hset(f"task:{task_id}", mapping={
            "status": "completed",
            "progress": 100,
            "message": "Transcription completed successfully",
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Set expiration on task hash (24 hours)
        redis_client.expire(f"task:{task_id}", 86400)
        
        print("=" * 80)
        print(f"✅ WORKER COMPLETED: task_id={task_id}")
        print(f"   Processing time: {(end_time - start_time).total_seconds():.2f}s")
        print(f"   Status in Redis: completed")
        print("=" * 80)
        
        # Don't call progress() here - status is already set to "completed" above!
        
        # Cleanup local file
        try:
            if storage_path and local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)
                logger.info(f"Cleaned up: {local_file_path}")
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
        
        # Cleanup storage synchronously
        if storage_path and storage_service.use_minio and storage_service.minio_client:
            try:
                # Extract object key from S3 URI if needed
                object_key = storage_path
                if storage_path.startswith("s3://"):
                    parts = storage_path.replace("s3://", "").split("/", 1)
                    if len(parts) > 1:
                        object_key = parts[1]
                
                storage_service.minio_client.remove_object(
                    settings.minio_bucket_name,
                    object_key  # Use extracted object key, not full URI
                )
                logger.info(f"Deleted from storage: {storage_path}")
            except Exception as e:
                logger.warning(f"Storage cleanup failed: {e}")
        
        return formatted_result
        
    except Exception as e:
        import traceback
        error_msg = f"Transcription failed: {str(e)}"
        error_trace = traceback.format_exc()
        
        print("=" * 80)
        print(f"❌ WORKER FAILED: task_id={task_id}")
        print(f"   Error: {error_msg}")
        print(f"   Traceback:\n{error_trace}")
        print("=" * 80)
        
        update_progress(task_id, 0, error_msg, status="failed")
        logger.error(f"{error_msg}\n{error_trace}")
        
        # Cleanup on error
        try:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)
        except:
            pass
        
        raise Exception(error_msg)