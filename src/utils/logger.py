"""
Centralized logging configuration for the audio diarization service
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional
from pathlib import Path

from ..config import settings

class AudioDiarizationLogger:
    """Centralized logger for the application"""
    
    _instance: Optional['AudioDiarizationLogger'] = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._setup_logger()
            AudioDiarizationLogger._initialized = True
    
    def _setup_logger(self):
        """Configure the logger with appropriate handlers and formatters"""
        # Determine logs directory (supports relative paths)
        log_dir = Path(settings.log_dir)
        if not log_dir.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            log_dir = project_root / log_dir

        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # File handler with rotation
        file_handler = RotatingFileHandler(
            filename=log_dir / "audio_diarization.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Error file handler
        error_handler = RotatingFileHandler(
            filename=log_dir / "errors.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)
        
        # Create application logger
        self.logger = logging.getLogger("audio_diarization")
        
        # Suppress verbose logs from third-party libraries
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("minio").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    def get_logger(self, name: str = None) -> logging.Logger:
        """Get a logger instance"""
        if name:
            return logging.getLogger(f"audio_diarization.{name}")
        return self.logger
    
    @classmethod
    def setup(cls) -> 'AudioDiarizationLogger':
        """Setup and return the logger instance"""
        return cls()

# Global logger instance
app_logger = AudioDiarizationLogger.setup()

def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance"""
    return app_logger.get_logger(name)