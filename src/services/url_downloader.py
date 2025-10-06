import yt_dlp
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
import re

class URLDownloader:
    """Handle downloading audio/video from various URL sources using yt-dlp"""
    
    def __init__(self, max_file_size: int = 500 * 1024 * 1024):  # 500MB
        self.max_file_size = max_file_size
        
    def _get_url_type(self, url: str) -> str:
        """Determine the type of URL"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        if 'youtube.com' in domain or 'youtu.be' in domain:
            return 'youtube'
        elif 'drive.google.com' in domain:
            return 'google_drive'
        elif 'dropbox.com' in domain:
            return 'dropbox'
        elif domain.endswith('.com') or domain.endswith('.org') or domain.endswith('.net'):
            return 'generic_web'
        else:
            return 'unknown'
    
    async def download_from_url(self, url: str, task_id: str, upload_dir: str) -> Tuple[str, str]:
        """
        Download audio/video from URL using yt-dlp
        Returns: (file_path, original_filename)
        """
        try:
            url_type = self._get_url_type(url)
            
            # Create temporary directory for download
            temp_dir = tempfile.mkdtemp()
            output_template = os.path.join(temp_dir, f"{task_id}_%(title)s.%(ext)s")
            
            # Configure yt-dlp options based on URL type
            ydl_opts = self._get_ydl_options(url_type, output_template)
            
            # Download the file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Get info first to check file size and format
                try:
                    info = ydl.extract_info(url, download=False)
                    
                    # Check if it's audio/video content
                    if not self._is_audio_video_content(info):
                        raise Exception("URL does not contain audio or video content")
                    
                    # Check file size if available
                    filesize = info.get('filesize') or info.get('filesize_approx')
                    if filesize and filesize > self.max_file_size:
                        raise Exception(f"File too large: {filesize/1024/1024:.1f}MB (max: {self.max_file_size/1024/1024:.1f}MB)")
                    
                    # Download the file
                    ydl.download([url])
                    
                except yt_dlp.DownloadError as e:
                    raise Exception(f"Failed to download from {url_type}: {str(e)}")
            
            # Find the downloaded file
            downloaded_files = list(Path(temp_dir).glob(f"{task_id}_*"))
            if not downloaded_files:
                raise Exception("No file was downloaded")
            
            downloaded_file = downloaded_files[0]
            
            # Check actual file size
            actual_size = downloaded_file.stat().st_size
            if actual_size > self.max_file_size:
                downloaded_file.unlink()  # Remove the file
                raise Exception(f"Downloaded file too large: {actual_size/1024/1024:.1f}MB")
            
            # Move to upload directory
            final_path = os.path.join(upload_dir, f"{task_id}_{downloaded_file.name}")
            os.rename(str(downloaded_file), final_path)
            
            # Clean up temp directory
            os.rmdir(temp_dir)
            
            return final_path, downloaded_file.name
            
        except Exception as e:
            # Clean up on error
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise Exception(f"URL download failed: {str(e)}")
    
    def _get_ydl_options(self, url_type: str, output_template: str) -> dict:
        """Get yt-dlp options based on URL type"""
        base_opts = {
            'outtmpl': output_template,
            'format': 'best[ext=mp4]/best[ext=webm]/best[ext=mkv]/best',  # Prefer common formats
            'noplaylist': True,  # Only download single video, not playlists
            'max_filesize': self.max_file_size,
        }
        
        if url_type == 'youtube':
            base_opts.update({
                'format': 'best[height<=720]/best',  # I don;'t need high quality of video, i only seek audio
                'writesubtitles': False,
                'writeautomaticsub': False,
            })
        elif url_type == 'google_drive':
            base_opts.update({
                'format': 'best',
                'nocheckcertificate': True,
            })
        elif url_type == 'dropbox':
            base_opts.update({
                'format': 'best',
                'nocheckcertificate': True,
            })
        elif url_type == 'generic_web':
            base_opts.update({
                'format': 'best',
                'nocheckcertificate': True,
            })
        
        return base_opts
    
    def _is_audio_video_content(self, info: dict) -> bool:
        """Check if the extracted info represents audio/video content"""
        # Check for audio/video indicators
        if info.get('vcodec') != 'none' or info.get('acodec') != 'none':
            return True
        
        # Check duration (audio/video should have duration)
        if info.get('duration') and info.get('duration') > 0:
            return True
        
        # Check format name for audio/video indicators
        formats = info.get('formats', [])
        for fmt in formats:
            if fmt.get('vcodec') != 'none' or fmt.get('acodec') != 'none':
                return True
        
        # Check file extension
        ext = info.get('ext', '').lower()
        audio_video_exts = {'mp4', 'mkv', 'webm', 'avi', 'mov', 'mp3', 'm4a', 'aac', 'wav', 'ogg', 'flac'}
        if ext in audio_video_exts:
            return True
        
        return False

# Global instance
url_downloader = URLDownloader()