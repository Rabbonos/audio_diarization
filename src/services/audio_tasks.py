"""
RQ task functions for audio processing
"""
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from .audio_processor import AudioProcessor
from .rq_task_manager import get_task_manager
from .result_service import result_service
from .storage_service import storage_service
from ..config import settings
from ..utils.logger import get_logger

# Get logger for this module
logger = get_logger("audio_tasks")

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
    RQ task function for processing audio transcription
    This runs in a separate worker process
    """
    # Get current job for progress tracking
    from rq import get_current_job
    
    job = get_current_job()
    task_id = job.id
    start_time = datetime.now()
    
    # Get task manager for progress updates
    task_manager = get_task_manager()
    
    def progress_callback(progress: float, message: str):
        """Synchronous progress callback for RQ job"""
        # Run async progress update in event loop
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                task_manager.update_task_progress(task_id, progress, message)
            )
            loop.close()
        except Exception as e:
            print(f"Error updating progress: {e}")
    
    try:
        # Initialize audio processor
        audio_processor = AudioProcessor()
        
        # Update progress
        progress_callback(0, "Starting transcription...")
        
        # Validate file exists
        if not file_path or not os.path.exists(file_path):
            raise Exception(f"Audio file not found: {file_path}")
        
        progress_callback(10, "Loading audio file...")
        
        # Process the audio synchronously
        result = asyncio.run(audio_processor.process_audio_sync(
            file_path=file_path,
            language=language,
            model=model,
            format_type=format_type,
            diarization=diarization,
            task_id=task_id,
            progress_callback=progress_callback
        ))
        
        progress_callback(95, "Storing results...")
        
        # Calculate processing time
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()
        
        # Store results in database and cache
        processing_metadata = {
            'started_at': start_time,
            'completed_at': end_time,
            'processing_time_seconds': processing_time,
            'original_filename': original_filename
        }
        
        # Store results using result service
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(
            result_service.store_transcription_result(
                task_id=task_id,
                api_token=api_token or "unknown",
                result_data=result,
                processing_metadata=processing_metadata
            )
        )
        loop.close()
        
        if not success:
            print(f"Warning: Failed to store results for task {task_id}")
        
        progress_callback(100, "Transcription completed successfully")
        
        # Clean up local temp audio file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up local audio file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up local audio file {file_path}: {e}")
        
        # Clean up audio file from storage (S3/MinIO)
        if storage_path:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                deleted = loop.run_until_complete(storage_service.delete_file(storage_path))
                loop.close()
                
                if deleted:
                    logger.info(f"Cleaned up storage file: {storage_path}")
                else:
                    logger.warning(f"Failed to delete storage file: {storage_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up storage file {storage_path}: {e}")
        
        return result
        
    except Exception as e:
        error_msg = f"Transcription failed: {str(e)}"
        progress_callback(0, error_msg)
        
        # Calculate processing time for failed task
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # Store error in database
        processing_metadata = {
            'started_at': start_time,
            'completed_at': end_time,
            'processing_time_seconds': processing_time,
            'original_filename': original_filename
        }
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                result_service.store_transcription_error(
                    task_id=task_id,
                    api_token=api_token or "unknown",
                    error_message=error_msg,
                    processing_metadata=processing_metadata
                )
            )
            loop.close()
        except Exception as store_error:
            print(f"Error storing failure result: {store_error}")
        
        # Clean up local temp audio file on error
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up local audio file after error: {file_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up local audio file after error: {cleanup_error}")
        
        # Clean up audio file from storage (S3/MinIO) on error
        if storage_path:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                deleted = loop.run_until_complete(storage_service.delete_file(storage_path))
                loop.close()
                
                if deleted:
                    logger.info(f"Cleaned up storage file after error: {storage_path}")
                else:
                    logger.warning(f"Failed to delete storage file after error: {storage_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up storage file after error {storage_path}: {e}")
        
        raise Exception(error_msg)