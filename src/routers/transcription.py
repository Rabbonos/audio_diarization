import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header
from typing import Literal, Optional
from ..config import settings
from ..auth import verify_api_key, ApiKeyDep
from ..services.audio_utils import get_audio_duration, convert_audio_to_wav_16khz
from ..services.rq_task_manager import get_task_manager
from ..services.url_downloader import url_downloader
from ..services.storage_service import storage_service
from ..services.result_service import result_service
from ..utils.logger import get_logger

router = APIRouter(prefix="/api/v1", tags=["transcription"])
logger = get_logger("transcription")

# Initialize task manager
task_manager = get_task_manager()

async def download_audio_from_url(url: str, task_id: str) -> str:
    """Download audio file from URL using yt-dlp for better support"""
    try:
        # Use the URL downloader service for comprehensive URL support
        file_path, original_filename = await url_downloader.download_from_url(
            url=url,
            task_id=task_id,
            upload_dir=settings.upload_dir
        )
        
        # Convert to 16kHz WAV for optimal Whisper processing
        wav_path = await convert_audio_to_wav_16khz(file_path)
        
        # Remove original file if conversion was successful and different
        if wav_path != file_path:
            os.remove(file_path)
        
        return wav_path
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download audio: {str(e)}")

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(None),
    url: str = Form(None),
    lang: str = Form("auto"),
    model: str = Form("tiny"),
    format: str = Form("json"),
    diarization: bool = Form(True),
    api_key: str = ApiKeyDep
):
    """
    Transcribe audio file or URL using Whisper and pyannote for diarization
    """
    try:
        # Validate input - either file or URL, not both
        if not file and not url:
            raise HTTPException(status_code=400, detail="Either file or URL must be provided")
        
        if file and url:
            raise HTTPException(status_code=400, detail="Provide either file or URL, not both")
        
        # Validate model parameter
        allowed_models = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "turbo"]
        if model not in allowed_models:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid model. Allowed: {allowed_models}"
            )
        
        # Validate language parameter
        if lang != "auto" and len(lang) != 2:
            raise HTTPException(
                status_code=400, 
                detail="Language must be 'auto' or 2-letter ISO code"
            )
        
        # Note: Concurrency is now controlled by worker count, not artificial limits
        # RQ will queue tasks if all workers are busy
        
        file_path = None
        storage_path = None  # Initialize storage path
        original_filename = None
        task_id = str(uuid.uuid4())  # Generate task ID upfront
        
        if file:
            # Handle file upload
            original_filename = file.filename
            
            # Validate file extension
            file_extension = Path(file.filename).suffix.lower()
            if file_extension not in settings.allowed_audio_extensions:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported file format. Allowed: {list(settings.allowed_audio_extensions)}"
                )
            
            # Check file size
            file.file.seek(0, 2)  # Seek to end
            file_size = file.file.tell()
            file.file.seek(0)  # Reset to beginning
            
            if file_size > settings.max_file_size:
                raise HTTPException(
                    status_code=413, 
                    detail=f"File too large. Maximum size: {settings.max_file_size/1024/1024:.1f}MB"
                )
            
            # Read file content once
            file_content = await file.read()
            
            # Save uploaded file using storage service (pass bytes directly)
            from io import BytesIO
            file_stream = BytesIO(file_content)
            storage_path = await storage_service.save_upload_file(file_stream, original_filename, task_id)
            
            # Download file for processing (will be local path or temp file)
            file_path = await storage_service.download_file(storage_path)
            
            # Convert to 16kHz WAV for optimal Whisper processing
            wav_file_path = await convert_audio_to_wav_16khz(file_path)
            
            # Get duration before uploading (wav_file_path is local)
            duration = await get_audio_duration(wav_file_path)
            
            # Upload converted WAV to storage for workers to access
            if wav_file_path != file_path:
                # Save converted WAV to storage
                try:
                    with open(wav_file_path, 'rb') as wav_f:
                        from io import BytesIO
                        wav_content = wav_f.read()
                        wav_stream = BytesIO(wav_content)
                        wav_storage_path = await storage_service.save_upload_file(
                            wav_stream, 
                            f"{task_id}_converted.wav", 
                            task_id
                        )
                except Exception as e:
                    logger.error(f"ERROR uploading converted WAV: {e}", exc_info=True)
                    raise
                
                # Clean up local temp files
                try:
                    if os.path.exists(file_path) and file_path != storage_path:
                        os.remove(file_path)
                    if os.path.exists(wav_file_path):
                        os.remove(wav_file_path)
                except:
                    pass
                
                # Use the storage path for the converted file
                storage_path = wav_storage_path
        
        elif url:
            # Handle URL download
            file_path = await download_audio_from_url(url, task_id)
            original_filename = Path(url).name or f"download{Path(file_path).suffix}"
            # Get duration for URL downloads
            duration = await get_audio_duration(file_path)
        
        # Validate duration
        try:
            if duration > settings.max_duration_seconds:
                raise HTTPException(
                    status_code=413, 
                    detail=f"Audio too long. Maximum duration: {settings.max_duration_hours} hours ({duration/3600:.1f} hours provided)"
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid audio file: {str(e)}")
        
        # Create initial database record
        file_size_bytes = None
        if file:
            file_size_bytes = len(file_content)
        
        request_metadata = {
            'original_filename': original_filename,
            'file_size_bytes': file_size_bytes,
            'language': lang,
            'model': model,
            'format_type': format,
            'diarization': diarization,
            'audio_duration_seconds': duration,
            'storage_path': storage_path if file else None
        }
        
        # Create initial database record
        await result_service.create_initial_record(
            task_id=task_id,
            api_token=api_key,
            request_metadata=request_metadata
        )
        
        # Create and queue the RQ task with all parameters
        # Pass task_id so RQ uses the same ID as the database record
        rq_task_id = await task_manager.create_task(
            task_id=task_id,  # Pass the task_id to ensure consistency
            file_path=file_path,
            storage_path=storage_path,  # Pass storage path for cleanup
            language=lang,
            model=model,
            format_type=format,
            diarization=diarization,
            original_filename=original_filename,
            api_token=api_key  # Pass API token to task
        )
        
        # Verify the task ID matches
        if rq_task_id != task_id:
            print(f"WARNING: RQ task ID ({rq_task_id}) doesn't match database ID ({task_id})")
        
        return {
            "task_id": task_id,
            "status": "queued",
            "message": "Audio file queued for processing",
            "estimated_duration": f"{duration/60:.1f} minutes"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR in transcribe endpoint: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/status/{task_id}")
async def get_task_status(task_id: str, api_key: str = Depends(verify_api_key)):
    """Get transcription task status with Redis → PostgreSQL fallback"""
    try:
        status = await result_service.get_task_status(task_id)
        
        print(f"📡 STATUS ENDPOINT: task_id={task_id}, result={status}")
        
        if not status:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving task status: {str(e)}")

@router.get("/result/{task_id}")
async def get_transcription_result(task_id: str, api_key: str = Depends(verify_api_key)):
    """
    Get full transcription result with Redis → PostgreSQL fallback
    
    Flow:
    1. Check Redis cache first (fast)
    2. If not found, check PostgreSQL database
    3. Cache database result in Redis for future requests
    """
    try:
        result = await result_service.get_transcription_result(task_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Transcription result not found")
        
        # Return appropriate response based on status
        if result['status'] == 'completed':
            return {
                'task_id': task_id,
                'status': 'completed',
                'result': result.get('result'),
                'transcription_text': result.get('transcription_text'),
                'metadata': result.get('metadata'),
                'source': result.get('source', 'cache')
            }
        elif result['status'] == 'failed':
            return {
                'task_id': task_id,
                'status': 'failed',
                'error': result.get('error'),
                'metadata': result.get('metadata'),
                'source': result.get('source', 'cache')
            }
        else:
            return {
                'task_id': task_id,
                'status': result['status'],
                'message': 'Task is still processing',
                'metadata': result.get('metadata'),
                'source': result.get('source', 'cache')
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving transcription result: {str(e)}")

@router.get("/history")
async def get_transcription_history(
    limit: int = 20,
    offset: int = 0,
    api_key: str = Depends(verify_api_key)
):
    """Get transcription history for the current API token"""
    try:
        if limit > 100:
            limit = 100  # Prevent excessive queries
            
        transcriptions = await result_service.list_user_transcriptions(
            api_token=api_key,
            limit=limit,
            offset=offset
        )
        
        return {
            'transcriptions': transcriptions,
            'count': len(transcriptions),
            'limit': limit,
            'offset': offset
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving transcription history: {str(e)}")

@router.delete("/result/{task_id}")
async def delete_transcription(task_id: str, api_key: str = Depends(verify_api_key)):
    """Delete a transcription result"""
    try:
        success = await result_service.delete_transcription(task_id, api_key)
        
        if not success:
            raise HTTPException(status_code=404, detail="Transcription not found or access denied")
        
        return {"message": "Transcription deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting transcription: {str(e)}")

@router.get("/result/{task_id}")
async def get_task_result(task_id: str, api_key: str = Depends(verify_api_key)):
    """Get transcription task result"""
    try:
        status = await task_manager.get_task_status(task_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if status["status"] != "completed":
            raise HTTPException(
                status_code=400, 
                detail=f"Task is {status['status']}, not completed"
            )
        
        result = status.get("result")
        if not result:
            raise HTTPException(status_code=404, detail="Result not found")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving task result: {str(e)}")

@router.delete("/cancel/{task_id}")
async def cancel_task(task_id: str, api_key: str = Depends(verify_api_key)):
    """Cancel a transcription task"""
    try:
        success = await task_manager.cancel_task(task_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Task not found or cannot be canceled")
        
        return {"message": "Task canceled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error canceling task: {str(e)}")