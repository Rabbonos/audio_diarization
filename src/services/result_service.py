"""
Result service for managing transcription results with Redis cache + PostgreSQL persistence
"""
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from ..config import settings
from .database_service import db_service
from ..utils.logger import get_logger
from ..utils.redis_client import get_redis_client

class ResultService:
    """
    Service for managing transcription results with caching strategy:
    1. Check Redis cache first (fast access)
    2. Fallback to PostgreSQL (persistent storage)
    3. Cache PostgreSQL results in Redis for future requests
    """
    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.cache_ttl = 3600 * 24  # 24 hours cache TTL
        self.logger = get_logger("result_service")
    
    def _get_cache_key(self, task_id: str, suffix: str = "") -> str:
        """Generate Redis cache key"""
        base_key = f"transcription_result:{task_id}"
        return f"{base_key}:{suffix}" if suffix else base_key
    
    async def store_transcription_result(
        self,
        task_id: str,
        api_token: str,
        result_data: Dict[str, Any],
        processing_metadata: Dict[str, Any]
    ) -> bool:
        """
        Store transcription result in both Redis cache and PostgreSQL
        
        Args:
            task_id: Unique task identifier
            api_token: API token used for the request
            result_data: Complete transcription result
            processing_metadata: Processing timing and metadata
        """
        try:
            # Extract data for database storage
            transcription_text = result_data.get('text', '')
            word_count = len(transcription_text.split()) if transcription_text else 0
            
            # Update PostgreSQL record
            success = await db_service.update_transcription_status(
                task_id=task_id,
                status='completed',
                started_at=processing_metadata.get('started_at'),
                completed_at=processing_metadata.get('completed_at'),
                processing_time_seconds=processing_metadata.get('processing_time_seconds'),
                detected_language=result_data.get('language'),
                transcription_text=transcription_text,
                formatted_result=result_data,
                word_count=word_count
            )
            
            if not success:
                self.logger.error(f"Failed to update database for task {task_id}")
                return False
            
            # Cache in Redis for fast access
            cache_data = {
                'task_id': task_id,
                'status': 'completed',
                'result': result_data,
                'metadata': processing_metadata,
                'cached_at': datetime.utcnow().isoformat()
            }
            
            self.redis_client.setex(
                self._get_cache_key(task_id),
                self.cache_ttl,
                json.dumps(cache_data, default=str)
            )
            
            # Update API usage stats
            await db_service.update_api_usage_stats(
                api_token=api_token,
                processing_time=processing_metadata.get('processing_time_seconds', 0),
                audio_duration=result_data.get('duration', 0),
                file_size_bytes=processing_metadata.get('file_size_bytes', 0),
                success=True
            )
            
            self.logger.info(f"✅ Stored transcription result for task {task_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error storing transcription result for task {task_id}: {e}")
            return False
    
    async def store_transcription_error(
        self,
        task_id: str,
        api_token: str,
        error_message: str,
        processing_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store transcription error in both Redis cache and PostgreSQL
        """
        try:
            # Update PostgreSQL record
            metadata = processing_metadata or {}
            success = await db_service.update_transcription_status(
                task_id=task_id,
                status='failed',
                started_at=metadata.get('started_at'),
                completed_at=datetime.utcnow(),
                processing_time_seconds=metadata.get('processing_time_seconds'),
                error_message=error_message
            )
            
            if not success:
                self.logger.error(f"Failed to update database error for task {task_id}")
                return False
            
            # Cache error in Redis
            cache_data = {
                'task_id': task_id,
                'status': 'failed',
                'error': error_message,
                'metadata': metadata,
                'cached_at': datetime.utcnow().isoformat()
            }
            
            self.redis_client.setex(
                self._get_cache_key(task_id),
                self.cache_ttl,
                json.dumps(cache_data, default=str)
            )
            
            # Update API usage stats (failed request)
            await db_service.update_api_usage_stats(
                api_token=api_token,
                processing_time=metadata.get('processing_time_seconds', 0),
                audio_duration=0,
                file_size_bytes=metadata.get('file_size_bytes', 0),
                success=False
            )
            
            self.logger.info(f"✅ Stored transcription error for task {task_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error storing transcription error for task {task_id}: {e}")
            return False
    
    async def get_transcription_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get transcription result with Redis → PostgreSQL fallback
        
        1. Check Redis cache first
        2. If not found, check PostgreSQL
        3. Cache PostgreSQL result in Redis for future requests
        """
        try:
            # Step 1: Check Redis cache
            cache_key = self._get_cache_key(task_id)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                self.logger.debug(f"🚀 Cache HIT for task {task_id}")
                return json.loads(cached_data)
            
            # Step 2: Check PostgreSQL
            self.logger.debug(f"💾 Cache MISS for task {task_id}, checking database...")
            db_result = await db_service.get_transcription_result(task_id)
            
            if not db_result:
                self.logger.warning(f"❌ Task {task_id} not found in database")
                return None
            
            # Step 3: Cache database result in Redis
            cache_data = {
                'task_id': task_id,
                'status': db_result['status'],
                'result': db_result.get('formatted_result'),
                'transcription_text': db_result.get('transcription_text'),
                'metadata': {
                    'created_at': db_result.get('created_at'),
                    'completed_at': db_result.get('completed_at'),
                    'processing_time_seconds': db_result.get('processing_time_seconds'),
                    'audio_duration_seconds': db_result.get('audio_duration_seconds'),
                    'word_count': db_result.get('word_count'),
                    'original_filename': db_result.get('original_filename'),
                    'language': db_result.get('language'),
                    'detected_language': db_result.get('detected_language'),
                    'model': db_result.get('model'),
                    'format_type': db_result.get('format_type')
                },
                'error': db_result.get('error_message'),
                'cached_at': datetime.utcnow().isoformat(),
                'source': 'database'
            }
            
            # Cache for future requests
            self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(cache_data, default=str)
            )
            
            self.logger.debug(f"✅ Cached database result for task {task_id}")
            return cache_data
            
        except Exception as e:
            self.logger.error(f"❌ Error getting transcription result for task {task_id}: {e}")
            return None
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task status (lighter version without full results)
        """
        try:
            # Check Redis first for active/recent tasks
            cache_key = self._get_cache_key(task_id)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data)
                return {
                    'task_id': task_id,
                    'status': data.get('status'),
                    'created_at': data.get('metadata', {}).get('created_at'),
                    'processing_time': data.get('metadata', {}).get('processing_time_seconds'),
                    'error': data.get('error'),
                    'source': 'cache'
                }
            
            # Check database for status
            db_result = await db_service.get_transcription_summary(task_id)
            if db_result:
                return {
                    'task_id': task_id,
                    'status': db_result['status'],
                    'created_at': db_result.get('created_at'),
                    'completed_at': db_result.get('completed_at'),
                    'processing_time': db_result.get('processing_time_seconds'),
                    'error': db_result.get('error_message'),
                    'source': 'database'
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting task status for {task_id}: {e}")
            return None
    
    async def list_user_transcriptions(
        self,
        api_token: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List transcriptions for a user (from database)
        """
        try:
            return await db_service.list_transcriptions_by_token(
                api_token=api_token,
                limit=limit,
                offset=offset
            )
        except Exception as e:
            self.logger.error(f"Error listing transcriptions for token: {e}")
            return []
    
    async def delete_transcription(self, task_id: str, api_token: str) -> bool:
        """
        Delete transcription from both cache and database
        """
        try:
            # Delete from Redis cache
            cache_key = self._get_cache_key(task_id)
            self.redis_client.delete(cache_key)
            
            # Delete from database
            success = await db_service.delete_transcription(task_id, api_token)
            
            if success:
                self.logger.info(f"✅ Deleted transcription {task_id}")
            else:
                self.logger.error(f"❌ Failed to delete transcription {task_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error deleting transcription {task_id}: {e}")
            return False
    
    async def create_initial_record(
        self,
        task_id: str,
        api_token: str,
        request_metadata: Dict[str, Any]
    ) -> bool:
        """
        Create initial database record when task is created
        """
        try:
            success = await db_service.create_transcription_record(
                task_id=task_id,
                api_token=api_token,
                original_filename=request_metadata.get('original_filename'),
                file_size_bytes=request_metadata.get('file_size_bytes'),
                language=request_metadata.get('language', 'auto'),
                model=request_metadata.get('model', 'medium'),
                format_type=request_metadata.get('format_type', 'json'),
                diarization_enabled=request_metadata.get('diarization', True),
                audio_duration_seconds=request_metadata.get('audio_duration_seconds'),
                storage_path=request_metadata.get('storage_path')
            )
            
            if success:
                self.logger.info(f"✅ Created initial record for task {task_id}")
            else:
                self.logger.error(f"❌ Failed to create initial record for task {task_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error creating initial record for task {task_id}: {e}")
            return False

# Global result service instance
result_service = ResultService()