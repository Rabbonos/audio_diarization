"""
Database models for transcription results and analytics
"""
from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, Dict, Any

class Base(DeclarativeBase):
    pass

class TranscriptionResult(Base):
    """
    Model for storing transcription results with metadata
    """
    __tablename__ = "transcription_results"
    
    # Primary identification
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)  # UUID
    
    # Request metadata
    api_token: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # API key used
    original_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # Original file name
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # File size in bytes
    
    # Processing metadata
    language: Mapped[str] = mapped_column(String(10), nullable=False)  # Language code or 'auto'
    model: Mapped[str] = mapped_column(String(50), nullable=False)  # Whisper model used
    format_type: Mapped[str] = mapped_column(String(20), nullable=False)  # Output format requested
    diarization_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Timing information
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # When processing started
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # When processing completed
    processing_time_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Total processing time
    
    # Audio metadata
    audio_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Duration of audio
    detected_language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # Detected language (if auto)
    
    # Results
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='queued')  # queued, processing, completed, failed
    transcription_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Plain text transcription
    formatted_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # Full structured result (segments, speakers, etc.)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Number of words transcribed
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Error message if failed
    
    # Storage information
    storage_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # Path to stored audio file
    
    def __repr__(self):
        return f"<TranscriptionResult(task_id='{self.task_id}', status='{self.status}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'task_id': self.task_id,
            'status': self.status,
            'original_filename': self.original_filename,
            'language': self.language,
            'detected_language': self.detected_language,
            'model': self.model,
            'format_type': self.format_type,
            'diarization_enabled': self.diarization_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time_seconds': self.processing_time_seconds,
            'audio_duration_seconds': self.audio_duration_seconds,
            'transcription_text': self.transcription_text,
            'formatted_result': self.formatted_result,
            'word_count': self.word_count,
            'error_message': self.error_message,
            'file_size_bytes': self.file_size_bytes
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary without full transcription text for listing"""
        return {
            'task_id': self.task_id,
            'status': self.status,
            'original_filename': self.original_filename,
            'language': self.language,
            'detected_language': self.detected_language,
            'model': self.model,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time_seconds': self.processing_time_seconds,
            'audio_duration_seconds': self.audio_duration_seconds,
            'word_count': self.word_count,
            'file_size_bytes': self.file_size_bytes
        }

class ApiUsageStats(Base):
    """
    Model for tracking API usage statistics
    """
    __tablename__ = "api_usage_stats"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_token: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Usage counters
    requests_count: Mapped[int] = mapped_column(Integer, default=0)
    total_processing_time: Mapped[float] = mapped_column(Float, default=0.0)
    total_audio_duration: Mapped[float] = mapped_column(Float, default=0.0)
    total_file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    
    # Success/failure tracking
    successful_requests: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    
    def __repr__(self):
        return f"<ApiUsageStats(token='{self.api_token}', date='{self.date}')>"