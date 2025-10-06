from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime

class TranscribeRequest(BaseModel):
    """Schema for transcription request parameters"""
    lang: str = Field(default="auto", description="Language code or 'auto' for detection")
    model: str = Field(default="medium", description="Whisper model size")
    format: Literal["text", "json", "srt", "vtt", "pdf", "docx"] = Field(
        default="json", 
        description="Output format"
    )
    diarization: bool = Field(default=True, description="Enable speaker diarization")
    url: Optional[str] = Field(default=None, description="Audio file URL (alternative to file upload)")
    
    @validator('model')
    def validate_model(cls, v):
        allowed_models = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "turbo"]
        if v not in allowed_models:
            raise ValueError(f"Model must be one of: {allowed_models}")
        return v
    
    @validator('lang')
    def validate_lang(cls, v):
        if v != "auto" and len(v) != 2:
            raise ValueError("Language must be 'auto' or 2-letter ISO code")
        return v

class TaskStatusResponse(BaseModel):
    """Schema for task status response"""
    task_id: str
    status: Literal["queued", "processing", "done", "error"]
    progress: float = Field(ge=0, le=100, description="Progress percentage")
    eta_seconds: Optional[int] = Field(default=None, description="Estimated time to completion")
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

class TaskResultResponse(BaseModel):
    """Schema for task result response"""
    task_id: str
    status: str
    result: dict
    format: str
    created_at: str
    completed_at: Optional[str] = None
    content_type: Optional[str] = None