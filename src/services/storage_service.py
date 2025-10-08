"""
Storage Service for handling file operations with MinIO S3 or local filesystem
"""
import os
import tempfile
import uuid
from typing import Optional, Tuple, BinaryIO
from pathlib import Path
import aiofiles
from minio import Minio
from minio.error import S3Error
from ..config import settings

class StorageService:
    """
    Unified storage service supporting both MinIO S3 and local filesystem
    """
    
    def __init__(self):
        self.use_minio = settings.use_minio
        self.minio_client = None
        
        if self.use_minio:
            self._init_minio()
    
    def _init_minio(self):
        """Initialize MinIO client and ensure bucket exists"""
        try:
            self.minio_client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            
            # Create bucket if it doesn't exist
            if not self.minio_client.bucket_exists(settings.minio_bucket_name):
                self.minio_client.make_bucket(settings.minio_bucket_name)
                print(f"Created MinIO bucket: {settings.minio_bucket_name}")
            
        except Exception as e:
            print(f"Warning: Failed to initialize MinIO: {e}")
            print("Falling back to local filesystem storage")
            self.use_minio = False
            self.minio_client = None
    
    async def save_upload_file(self, file: BinaryIO, original_filename: str, task_id: str) -> str:
        """
        Save uploaded file and return the storage path/key
        
        Args:
            file: File-like object to save
            original_filename: Original filename
            task_id: Unique task identifier
            
        Returns:
            Storage path/key for the saved file
        """
        # Generate unique filename
        file_extension = Path(original_filename).suffix.lower()
        storage_key = f"uploads/{task_id}_{uuid.uuid4()}{file_extension}"
        
        if self.use_minio and self.minio_client:
            return await self._save_to_minio(file, storage_key)
        else:
            return await self._save_to_local(file, storage_key)
    
    async def _save_to_minio(self, file: BinaryIO, storage_key: str) -> str:
        """Save file to MinIO S3"""
        try:
            # Read file content - handle different file types
            if hasattr(file, 'read'):
                read_method = file.read
                if callable(read_method):
                    import inspect
                    if inspect.iscoroutinefunction(read_method):
                        # Async read (FastAPI UploadFile)
                        content = await read_method()
                    else:
                        # Sync read (SpooledTemporaryFile, regular file, BytesIO)
                        content = read_method()
                else:
                    content = file
            else:
                # Already bytes
                content = file
            
            # Debug logging
            print(f"DEBUG: Content type: {type(content)}, Content length: {len(content) if content else 'None'}")
            
            # Handle empty content
            if content is None or (isinstance(content, bytes) and len(content) == 0):
                raise Exception("File content is empty")
            
            # Convert to bytes if needed
            if isinstance(content, str):
                content = content.encode()
            elif not isinstance(content, bytes):
                content = bytes(content)
            
            # MinIO put_object needs a file-like object with length
            from io import BytesIO
            data_stream = BytesIO(content)
            
            # Upload to MinIO
            self.minio_client.put_object(
                bucket_name=settings.minio_bucket_name,
                object_name=storage_key,
                data=data_stream,
                length=len(content)
            )
            
            return f"s3://{settings.minio_bucket_name}/{storage_key}"
            
        except Exception as e:
            import traceback
            print(f"ERROR in _save_to_minio: {e}")
            print(traceback.format_exc())
            raise Exception(f"Failed to save file to MinIO: {e}")
    
    async def _save_to_local(self, file: BinaryIO, storage_key: str) -> str:
        """Save file to local filesystem"""
        try:
            # Ensure upload directory exists
            os.makedirs(settings.upload_dir, exist_ok=True)
            
            # Create local file path
            local_path = os.path.join(settings.upload_dir, os.path.basename(storage_key))
            
            # Read file content - handle different file types
            if hasattr(file, 'read'):
                read_method = file.read
                if callable(read_method):
                    import inspect
                    if inspect.iscoroutinefunction(read_method):
                        # Async read (FastAPI UploadFile)
                        content = await read_method()
                    else:
                        # Sync read (SpooledTemporaryFile, regular file)
                        content = read_method()
                else:
                    content = file
            else:
                # Already bytes
                content = file
            
            # Handle empty content
            if content is None or (isinstance(content, bytes) and len(content) == 0):
                raise Exception("File content is empty")
            
            # Write content to file
            async with aiofiles.open(local_path, 'wb') as f:
                await f.write(content)
            
            return local_path
            
        except Exception as e:
            raise Exception(f"Failed to save file locally: {e}")
    
    async def download_file(self, storage_path: str) -> str:
        """
        Download file to temporary location and return local path
        
        Args:
            storage_path: Storage path/key or S3 URL
            
        Returns:
            Local file path for processing
        """
        if storage_path.startswith("s3://"):
            return await self._download_from_minio(storage_path)
        else:
            # Already a local path
            return storage_path
    
    async def _download_from_minio(self, s3_url: str) -> str:
        """Download file from MinIO S3 to temporary location"""
        try:
            # Parse S3 URL: s3://bucket/key
            parts = s3_url.replace("s3://", "").split("/", 1)
            bucket_name = parts[0]
            object_name = parts[1]
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(object_name).suffix)
            temp_path = temp_file.name
            temp_file.close()
            
            # Download from MinIO
            self.minio_client.fget_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=temp_path
            )
            
            return temp_path
            
        except Exception as e:
            raise Exception(f"Failed to download file from MinIO: {e}")
    
    async def delete_file(self, storage_path: str) -> bool:
        """
        Delete file from storage
        
        Args:
            storage_path: Storage path/key or S3 URL
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if storage_path.startswith("s3://"):
                return await self._delete_from_minio(storage_path)
            else:
                return await self._delete_from_local(storage_path)
        except Exception as e:
            print(f"Warning: Failed to delete file {storage_path}: {e}")
            return False
    
    async def _delete_from_minio(self, s3_url: str) -> bool:
        """Delete file from MinIO S3"""
        try:
            # Parse S3 URL
            parts = s3_url.replace("s3://", "").split("/", 1)
            bucket_name = parts[0]
            object_name = parts[1]
            
            # Delete from MinIO
            self.minio_client.remove_object(
                bucket_name=bucket_name,
                object_name=object_name
            )
            
            return True
            
        except Exception as e:
            print(f"Failed to delete file from MinIO: {e}")
            return False
    
    async def _delete_from_local(self, file_path: str) -> bool:
        """Delete file from local filesystem"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
            
        except Exception as e:
            print(f"Failed to delete local file: {e}")
            return False
    
    def get_file_url(self, storage_path: str) -> str:
        """
        Get accessible URL for file (for MinIO web access)
        
        Args:
            storage_path: Storage path/key or S3 URL
            
        Returns:
            Accessible URL
        """
        if storage_path.startswith("s3://") and self.minio_client:
            # Parse S3 URL
            parts = storage_path.replace("s3://", "").split("/", 1)
            bucket_name = parts[0]
            object_name = parts[1]
            
            # Generate presigned URL (valid for 1 hour)
            try:
                url = self.minio_client.presigned_get_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    expires=3600  # 1 hour
                )
                return url
            except Exception:
                return storage_path
        
        return storage_path

# Global storage service instance
storage_service = StorageService()