#!/usr/bin/env python3
"""
S3/MinIO Cleanup Script
Removes old uploaded audio files to prevent storage accumulation
Run this as a cron job or scheduled task
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from minio import Minio
from minio.error import S3Error
from src.config import settings

# Retention period - files older than this will be deleted
RETENTION_DAYS = int(os.getenv("S3_RETENTION_DAYS", "7"))  # Default 7 days

def cleanup_old_files():
    """Remove files older than retention period from MinIO"""
    
    if not settings.use_minio:
        print("MinIO is not enabled. Skipping cleanup.")
        return
    
    try:
        # Initialize MinIO client
        client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        
        print("=" * 60)
        print("MinIO S3 Cleanup")
        print("=" * 60)
        print(f"Bucket: {settings.minio_bucket_name}")
        print(f"Retention period: {RETENTION_DAYS} days")
        print(f"Current time: {datetime.now()}")
        print("=" * 60)
        
        # Check if bucket exists
        if not client.bucket_exists(settings.minio_bucket_name):
            print(f"✗ Bucket '{settings.minio_bucket_name}' does not exist")
            return
        
        # Calculate cutoff time
        cutoff_time = datetime.now() - timedelta(days=RETENTION_DAYS)
        print(f"Deleting files older than: {cutoff_time}")
        print("")
        
        # List all objects in bucket
        objects = client.list_objects(
            settings.minio_bucket_name,
            prefix="uploads/",  # Only check uploaded files
            recursive=True
        )
        
        deleted_count = 0
        deleted_size = 0
        skipped_count = 0
        
        for obj in objects:
            # Get object stat to check last modified time
            try:
                stat = client.stat_object(settings.minio_bucket_name, obj.object_name)
                last_modified = stat.last_modified
                
                # Remove timezone info for comparison
                if last_modified.tzinfo:
                    last_modified = last_modified.replace(tzinfo=None)
                
                # Check if file is old enough to delete
                if last_modified < cutoff_time:
                    # Calculate age
                    age_days = (datetime.now() - last_modified).days
                    size_mb = obj.size / (1024 * 1024)
                    
                    print(f"Deleting: {obj.object_name}")
                    print(f"  Age: {age_days} days | Size: {size_mb:.2f} MB")
                    
                    # Delete the object
                    client.remove_object(settings.minio_bucket_name, obj.object_name)
                    
                    deleted_count += 1
                    deleted_size += obj.size
                else:
                    skipped_count += 1
                    
            except Exception as e:
                print(f"✗ Error processing {obj.object_name}: {e}")
        
        # Summary
        print("")
        print("=" * 60)
        print("Cleanup Complete")
        print("=" * 60)
        print(f"✓ Deleted files: {deleted_count}")
        print(f"✓ Freed space: {deleted_size / (1024 * 1024):.2f} MB ({deleted_size / (1024 * 1024 * 1024):.2f} GB)")
        print(f"  Kept files: {skipped_count} (within retention period)")
        print("=" * 60)
        
    except S3Error as e:
        print(f"✗ MinIO error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        sys.exit(1)

def main():
    """Main cleanup function"""
    try:
        cleanup_old_files()
    except KeyboardInterrupt:
        print("\nCleanup interrupted by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
