import whisper
import torch
from pyannote.audio import Pipeline
import subprocess
import json
import os
import time
from datetime import timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path
from ..config import settings
from .audio_utils import convert_audio_if_needed
from .model_cache import model_cache
from .resource_manager import ResourceManager

class AudioProcessor:
    def __init__(self):
        self.whisper_model = None
        self.diarization_pipeline = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.resource_manager = ResourceManager()
        self.current_model_name = None
        
    async def load_models(self, model_name: str = "medium"):
        """Load Whisper and pyannote models with smart caching and resource management"""
        try:
            # Check resource availability and get best available model
            if not self.resource_manager.can_load_model(model_name):
                suggested_model = self.resource_manager.suggest_best_model()
                print(f"Cannot load {model_name} due to resource constraints. Using {suggested_model} instead.")
                model_name = suggested_model
            
            # Load Whisper model using cache
            if not self.whisper_model or self.current_model_name != model_name:
                print(f"Loading Whisper model: {model_name}")
                
                # Get cached model with resource management
                cached_model = model_cache.get_model(model_name)
                
                # Move to appropriate device for processing
                self.whisper_model = model_cache.move_to_device(cached_model, self.device)
                self.current_model_name = model_name
            
            # Load pyannote diarization pipeline (only once)
            if not self.diarization_pipeline:
                print("Loading pyannote diarization pipeline")
                self.diarization_pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=settings.hf_token  # Changed from use_auth_token to token
                )
                if torch.cuda.is_available():
                    self.diarization_pipeline.to(torch.device("cuda"))
                    
        except Exception as e:
            raise Exception(f"Failed to load models: {str(e)}")
    
    def cleanup_gpu_memory(self):
        """Clean up GPU memory after processing"""
        if self.whisper_model and torch.cuda.is_available():
            # Move model back to CPU and clear GPU cache
            self.whisper_model = model_cache.release_gpu_memory(self.whisper_model, self.current_model_name)
            
        if self.diarization_pipeline and torch.cuda.is_available():
            # Clear any remaining GPU memory
            torch.cuda.empty_cache()
    
    async def process_audio(self, task_id: str, file_path: str, language: str = "auto", 
                          model: str = "medium", format: str = "json", 
                          diarization: bool = True, task_manager=None) -> Dict[str, Any]:
        """Process audio file with progress tracking"""
        try:
            if task_manager:
                await task_manager.update_task_status(task_id, "processing")
                await task_manager.update_task_progress(task_id, 5.0)
            
            # Convert audio if needed (for wma/wmv)
            file_path = await convert_audio_if_needed(file_path)
            
            # Load models
            await self.load_models(model)
            if task_manager:
                await task_manager.update_task_progress(task_id, 15.0)
            
            # Get file duration for ETA calculation
            duration_info = await self._get_file_info(file_path)
            total_duration = duration_info['duration']
            
            # Estimate processing time (roughly real-time for transcription + 30% for diarization)
            estimated_processing_time = total_duration * (1.3 if diarization else 1.0)
            
            # Transcribe with Whisper
            if task_manager:
                await task_manager.update_task_progress(task_id, 20.0, 
                                                      int(estimated_processing_time * 0.7))
            
            transcription_result = await self._transcribe_audio(task_id, file_path, language)
            if task_manager:
                await task_manager.update_task_progress(task_id, 60.0, 
                                                      int(estimated_processing_time * 0.4))
            
            # Perform diarization if requested
            speakers_info = None
            if diarization:
                speakers_info = await self._perform_diarization(task_id, file_path)
                if task_manager:
                    await task_manager.update_task_progress(task_id, 80.0, 
                                                          int(estimated_processing_time * 0.2))
            
            # Combine results
            combined_result = await self._combine_results(
                transcription_result, speakers_info, total_duration
            )
            if task_manager:
                await task_manager.update_task_progress(task_id, 100.0, 0)
            
            # Return raw data only - formatting will be done on-demand
            return combined_result
            
        except Exception as e:
            if task_manager:
                await task_manager.update_task_status(
                    task_id, "error", error_message=str(e)
                )
            raise
        finally:
            # Always clean up GPU memory after processing
            self.cleanup_gpu_memory()
            # Clean up file
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass  # Ignore cleanup errors
    
    async def process_audio_sync(self, file_path: str, language: str = "auto", 
                                model: str = "medium", format_type: str = "json", 
                                diarization: bool = True, task_id: str = None,
                                progress_callback = None) -> Dict[str, Any]:
        """Synchronous version of process_audio for RQ workers"""
        try:
            if progress_callback:
                progress_callback(5.0, "Starting audio processing...")
            
            # Convert audio if needed (for wma/wmv)
            file_path = await convert_audio_if_needed(file_path)
            
            # Load models
            await self.load_models(model)
            if progress_callback:
                progress_callback(15.0, "Models loaded, analyzing audio...")
            
            # Get file duration for ETA calculation
            duration_info = await self._get_file_info(file_path)
            total_duration = duration_info['duration']
            
            # Transcribe with Whisper
            if progress_callback:
                progress_callback(20.0, "Transcribing audio...")
            
            transcription_result = await self._transcribe_audio(task_id, file_path, language)
            if progress_callback:
                progress_callback(60.0, "Transcription complete, processing speakers...")
            
            # Perform diarization if requested
            speakers_info = None
            if diarization:
                speakers_info = await self._perform_diarization(task_id, file_path)
                if progress_callback:
                    progress_callback(80.0, "Speaker diarization complete, formatting results...")
            
            # Combine results
            combined_result = await self._combine_results(
                transcription_result, speakers_info, total_duration
            )
            if progress_callback:
                progress_callback(100.0, "Processing complete")
            
            # Return raw data only - formatting will be done on-demand
            return combined_result
            
        except Exception as e:
            if progress_callback:
                progress_callback(0, f"Error: {str(e)}")
            raise
        finally:
            # Always clean up GPU memory after processing
            self.cleanup_gpu_memory()

    async def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get file information using ffprobe"""
        cmd = [
            'ffprobe', '-v', 'quiet', '-show_format', '-show_streams',
            '-of', 'json', file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        return {
            'duration': float(data['format']['duration']),
            'size': int(data['format']['size']),
            'bitrate': int(data['format'].get('bit_rate', 0))
        }
    
    async def _transcribe_audio(self, task_id: str, file_path: str, 
                              language: str) -> Dict[str, Any]:
        """Transcribe audio using Whisper"""
        language_param = None if language == "auto" else language
        
        result = self.whisper_model.transcribe(
            file_path,
            language=language_param,
            verbose=False
        )
        
        return result
    
    async def _perform_diarization(self, task_id: str, file_path: str) -> Dict[str, Any]:
        """Perform speaker diarization using pyannote"""
        try:
            # pyannote 3.1 returns a DiarizeOutput object
            output = self.diarization_pipeline(file_path)
            
            # The diarization is in output.speaker_diarization (an Annotation object)
            diarization = output.speaker_diarization
            
            speakers = {}
            # Iterate over the annotation: (segment, track, label) tuples
            for turn, track, speaker in diarization.itertracks(yield_label=True):
                speaker_id = f"SPEAKER_{speaker}"
                if speaker_id not in speakers:
                    speakers[speaker_id] = []
                
                speakers[speaker_id].append({
                    "start": float(turn.start),
                    "end": float(turn.end),
                    "duration": float(turn.end - turn.start)
                })
            
            return speakers
            
        except Exception as e:
            print(f"Diarization failed: {e}")
            import traceback
            print(traceback.format_exc())
            return {}
    
    async def _combine_results(self, transcription: Dict[str, Any], 
                             speakers: Optional[Dict[str, Any]], 
                             duration: float) -> Dict[str, Any]:
        """Combine transcription and diarization results"""
        segments = transcription.get('segments', [])
        
        if speakers:
            # Map speakers to segments based on timing
            for segment in segments:
                segment['speaker'] = self._find_speaker_for_segment(
                    segment, speakers
                )
        
        return {
            'text': transcription.get('text', ''),
            'language': transcription.get('language', 'unknown'),
            'segments': segments,
            'speakers': speakers,
            'duration': duration,
            'word_count': len(transcription.get('text', '').split()),
        }
    
    def _find_speaker_for_segment(self, segment: Dict[str, Any], 
                                speakers: Dict[str, Any]) -> str:
        """Find the most likely speaker for a segment"""
        segment_start = segment.get('start', 0)
        segment_end = segment.get('end', 0)
        segment_mid = (segment_start + segment_end) / 2
        
        for speaker_id, turns in speakers.items():
            for turn in turns:
                if turn['start'] <= segment_mid <= turn['end']:
                    return speaker_id
        
        return "SPEAKER_UNKNOWN"