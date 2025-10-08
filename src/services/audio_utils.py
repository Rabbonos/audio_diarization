import subprocess
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

async def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe"""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'quiet', 
            '-show_entries', 'format=duration', 
            '-of', 'json', 
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        duration = float(data['format']['duration'])
        return duration
        
    except (subprocess.CalledProcessError, KeyError, ValueError, json.JSONDecodeError) as e:
        raise Exception(f"Could not determine audio duration: {str(e)}")

async def validate_audio_file(file_path: str) -> bool:
    """Validate that the file is a valid audio/video file"""
    try:
        if not os.path.exists(file_path):
            return False
            
        cmd = [
            'ffprobe', 
            '-v', 'quiet', 
            '-show_entries', 'stream=codec_type', 
            '-of', 'json', 
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        # Check if file has audio stream
        streams = data.get('streams', [])
        has_audio = any(stream.get('codec_type') == 'audio' for stream in streams)
        
        return has_audio
        
    except Exception:
        return False

async def convert_audio_to_wav_16khz(file_path: str) -> str:
    """Convert audio to 16kHz WAV PCM mono for Whisper processing"""
    try:
        # Create temporary output file
        fd, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)  # Close the file descriptor
        
        cmd = [
            'ffmpeg', 
            '-i', file_path,
            '-acodec', 'pcm_s16le',  # PCM 16-bit
            '-ac', '1',              # mono
            '-ar', '16000',          # 16kHz sample rate
            '-y',                    # Overwrite output file
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to convert audio to 16kHz WAV: {str(e)}")

async def convert_audio_if_needed(file_path: str) -> str:
    """Convert audio to supported format if needed (for wma/wmv files)"""
    try:
        # Check if conversion is needed for wma/wmv files
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in ['.wma', '.wmv']:
            # Convert to mp3 for better compatibility, then to 16kHz WAV
            temp_mp3 = file_path.replace(file_ext, '.mp3')
            
            cmd = [
                'ffmpeg', 
                '-i', file_path,
                '-acodec', 'mp3',
                '-ab', '192k',
                '-y',  # Overwrite output file
                temp_mp3
            ]
            
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Remove original file
            os.remove(file_path)
            
            # Now convert to 16kHz WAV
            wav_output = await convert_audio_to_wav_16khz(temp_mp3)
            
            # Remove intermediate mp3
            os.remove(temp_mp3)
            
            return wav_output
        else:
            # Convert directly to 16kHz WAV
            wav_output = await convert_audio_to_wav_16khz(file_path)
            
            # Remove original file
            os.remove(file_path)
            
            return wav_output
        
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to convert audio file: {str(e)}")

async def get_file_size_from_url(url: str) -> Optional[int]:
    """Get file size from URL without downloading (HEAD request)"""
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.head(url)
            content_length = response.headers.get('content-length')
            if content_length:
                return int(content_length)
    except Exception:
        pass
    
    return None