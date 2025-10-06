"""
Database service for managing transcription results
"""
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import json

from ..config import settings
from ..models import Base, TranscriptionResult, ApiUsageStats

class DatabaseService:
    """
    Service for managing transcription results in PostgreSQL
    """
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialize_db()
    
    def _initialize_db(self):
        """Initialize database connection and create tables"""
        try:
            self.engine = create_engine(
                settings.database_url,
                echo=False,  # Set to True for SQL debugging
                pool_pre_ping=True,
                pool_recycle=300
            )
            
            # Create all tables
            Base.metadata.create_all(bind=self.engine)
            
            # Create session factory
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            
            print("✅ Database initialized successfully")
            
        except Exception as e:
            print(f"❌ Database initialization failed: {e}")
            raise
    
    async def create_transcription_record(
        self,
        task_id: str,
        api_token: str,
        original_filename: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        language: str = "auto",
        model: str = "medium",
        format_type: str = "json",
        diarization_enabled: bool = True,
        audio_duration_seconds: Optional[float] = None,
        storage_path: Optional[str] = None
    ) -> bool:
        """
        Create initial transcription record using built-in Session context manager
        """
        try:
            with self.SessionLocal() as session:
                transcription = TranscriptionResult(
                    task_id=task_id,
                    api_token=api_token,
                    original_filename=original_filename,
                    file_size_bytes=file_size_bytes,
                    language=language,
                    model=model,
                    format_type=format_type,
                    diarization_enabled=diarization_enabled,
                    audio_duration_seconds=audio_duration_seconds,
                    storage_path=storage_path,
                    status='queued',
                    created_at=datetime.utcnow()
                )
                
                session.add(transcription)
                session.commit()
            
            return True
            
        except Exception as e:
            print(f"Database error creating transcription record: {e}")
            return False
    
    async def update_transcription_status(
        self,
        task_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        processing_time_seconds: Optional[float] = None,
        detected_language: Optional[str] = None,
        transcription_text: Optional[str] = None,
        formatted_result: Optional[Dict[str, Any]] = None,
        word_count: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update transcription record with results using built-in Session context manager
        """
        try:
            with self.SessionLocal() as session:
                transcription = session.query(TranscriptionResult).filter(
                    TranscriptionResult.task_id == task_id
                ).first()
                
                if not transcription:
                    print(f"Transcription record not found: {task_id}")
                    return False
                
                # Update fields
                transcription.status = status
                if started_at:
                    transcription.started_at = started_at
                if completed_at:
                    transcription.completed_at = completed_at
                if processing_time_seconds is not None:
                    transcription.processing_time_seconds = processing_time_seconds
                if detected_language:
                    transcription.detected_language = detected_language
                if transcription_text:
                    transcription.transcription_text = transcription_text
                if formatted_result:
                    transcription.formatted_result = formatted_result
                if word_count is not None:
                    transcription.word_count = word_count
                if error_message:
                    transcription.error_message = error_message
                
                session.commit()
            
            return True
            
        except Exception as e:
            print(f"Database error updating transcription: {e}")
            return False
    
    async def get_transcription_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get transcription result by task ID using built-in Session context manager
        """
        try:
            with self.SessionLocal() as session:
                transcription = session.query(TranscriptionResult).filter(
                    TranscriptionResult.task_id == task_id
                ).first()
                
                if transcription:
                    return transcription.to_dict()
                return None
                
        except Exception as e:
            print(f"Error getting transcription result: {e}")
            return None
    
    async def get_transcription_summary(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get transcription summary (without full text) by task ID
        """
        try:
            with self.SessionLocal() as session:
                transcription = session.query(TranscriptionResult).filter(
                    TranscriptionResult.task_id == task_id
                ).first()
                
                if transcription:
                    return transcription.get_summary()
                return None
                
        except Exception as e:
            print(f"Error getting transcription summary: {e}")
            return None
    
    async def list_transcriptions_by_token(
        self,
        api_token: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List transcriptions for a specific API token using built-in Session context manager
        """
        try:
            with self.SessionLocal() as session:
                transcriptions = session.query(TranscriptionResult).filter(
                    TranscriptionResult.api_token == api_token
                ).order_by(
                    TranscriptionResult.created_at.desc()
                ).offset(offset).limit(limit).all()
                
                return [t.get_summary() for t in transcriptions]
                
        except Exception as e:
            print(f"Error listing transcriptions: {e}")
            return []
    
    async def delete_transcription(self, task_id: str, api_token: str) -> bool:
        """
        Delete transcription record (with token verification) using built-in Session context manager
        """
        try:
            with self.SessionLocal() as session:
                result = session.query(TranscriptionResult).filter(
                    TranscriptionResult.task_id == task_id,
                    TranscriptionResult.api_token == api_token
                ).delete()
                
                session.commit()
                return result > 0
                
        except Exception as e:
            print(f"Error deleting transcription: {e}")
            return False
    
    async def update_api_usage_stats(
        self,
        api_token: str,
        processing_time: float = 0.0,
        audio_duration: float = 0.0,
        file_size_bytes: int = 0,
        success: bool = True
    ):
        """
        Update API usage statistics using built-in Session context manager
        """
        try:
            with self.SessionLocal() as session:
                # Get today's date for stats aggregation
                today = datetime.utcnow().date()
                
                # Find or create today's stats record
                stats = session.query(ApiUsageStats).filter(
                    ApiUsageStats.api_token == api_token,
                    ApiUsageStats.date >= today
                ).first()
                
                if not stats:
                    stats = ApiUsageStats(
                        api_token=api_token,
                        date=datetime.utcnow()
                    )
                    session.add(stats)
                
                # Update counters
                stats.requests_count += 1
                stats.total_processing_time += processing_time
                stats.total_audio_duration += audio_duration
                stats.total_file_size_bytes += file_size_bytes
                
                if success:
                    stats.successful_requests += 1
                else:
                    stats.failed_requests += 1
                
                session.commit()
                
        except Exception as e:
            print(f"Error updating API usage stats: {e}")

# Global database service instance
db_service = DatabaseService()

# Global database service instance
db_service = DatabaseService()