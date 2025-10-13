# 🎵 Audio Diarization Service MVP

A cloud service for automatic audio transcription and speaker diarization using Whisper and pyannote.audio.

## ✨ Features

- **Multi-language transcription** using OpenAI Whisper
- **Speaker diarization** using pyannote.audio
- **Multiple output formats**: text, JSON, SRT, VTT
- **Async processing** with Redis task queue
- **RESTful API** with FastAPI
- **Monitoring** with Prometheus & Grafana
- **Containerized** with Docker Compose

## 🏗️ Architecture

![Audio Diarization MVP Architecture](./Audio%20Diarization%20MVP.drawio.svg)

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- HuggingFace account (for pyannote models)

### Setup

1. **Clone and navigate to the project**:
   ```bash
   cd audio_diarization
   ```

2. **Get HuggingFace token**:
   - Go to [HuggingFace](https://huggingface.co/settings/tokens)
   - Create a new token with read permissions
   - Accept pyannote/speaker-diarization-3.1 model license

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your HF_TOKEN
   ```

4. **Start services**:
   ```bash
   ./setup.sh
   ```

## 📋 API Usage

### Authentication
All requests require API key in header:
```bash
Authorization: Bearer mvp-api-key-123
```

### Submit Transcription
```bash
curl -X POST "http://localhost:8000/api/v1/transcribe" \
  -H "Authorization: Bearer mvp-api-key-123" \
  -F "file=@audio.mp3" \
  -F "lang=auto" \
  -F "format=json" \
  -F "diarization=true"
```

**Response:**
```json
{
  "task_id": "uuid-here",
  "status": "queued",
  "message": "Task successfully created"
}
```

### Check Status
```bash
curl "http://localhost:8000/api/v1/status/{task_id}" \
  -H "Authorization: Bearer mvp-api-key-123"
```

**Response:**
```json
{
  "task_id": "uuid-here",
  "status": "processing",
  "progress": 42,
  "eta_seconds": 75
}
```

### Get Result
```bash
curl "http://localhost:8000/api/v1/result/{task_id}" \
  -H "Authorization: Bearer mvp-api-key-123"
```

**Response:**
```json
{
  "task_id": "uuid-here",
  "status": "done",
  "language": "en",
  "model": "medium",
  "segments": [
    {
      "start": 0.0,
      "end": 4.5,
      "speaker": "spk_1",
      "text": "Hello everyone, welcome to the meeting."
    }
  ],
  "full_text": "Complete transcription...",
  "processing_time": 12.34
}
```

## 🎛️ Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI application |
| Grafana | 3000 | Monitoring dashboard (admin/admin123) |
| Prometheus | 9090 | Metrics collection |
| Redis | 6379 | Task queue |
| PostgreSQL | 5432 | Database |

## 📁 Supported Formats

### Input
- **Audio**: mp3, m4a, aac, wav, mpeg, ogg, opus, flac
- **Video**: mp4, mov, avi, mpeg (audio extracted)

### Output
- **text**: Plain text
- **json**: Structured with timestamps and speakers
- **srt**: SubRip subtitle format
- **vtt**: WebVTT subtitle format

## ⚙️ Configuration

Key environment variables in `.env`:

```bash
# API Settings
API_KEY=mvp-api-key-123

# Model Settings
WHISPER_MODEL=medium
HF_TOKEN=your_huggingface_token

# Limits
MAX_FILE_SIZE=524288000  # 500MB
MAX_DURATION=28800       # 8 hours
MAX_WORKERS=2
```

## 🧪 Testing

Test with sample audio:
```bash
python test_api.py sample.mp3
```

## 📊 Monitoring

- **Grafana**: http://localhost:3000 (admin/admin123)
- **Prometheus**: http://localhost:9090
- **API Health**: http://localhost:8000/health

## 🐳 Docker Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f app
docker-compose logs -f worker

# Restart service
docker-compose restart app

# Stop all
docker-compose down

# Rebuild
docker-compose up --build -d
```

## 🔧 Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run API locally
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run worker locally
python -m src.worker
```

### Project Structure
```
├── src/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── models.py            # Data models
│   ├── worker.py            # Background worker
│   ├── routers/
│   │   └── transcription.py # API routes
│   └── services/
│       ├── audio_processor.py  # Whisper + pyannote
│       └── task_manager.py     # Redis task management
├── docker-compose.yaml      # Service orchestration
├── Dockerfile              # App container
├── requirements.txt        # Python dependencies
└── setup.sh               # Setup script
```

## 🚧 MVP Limitations

- Single API key authentication
- Local file storage (MinIo S3)
- Basic error handling
- Limited concurrent processing (2 workers)
- No user management
- No rate limiting

## 🔄 Next Steps

1. **Authentication**: OAuth2/JWT tokens
2. **Storage**: S3 integration
3. **Scaling**: Kubernetes deployment
4. **Monitoring**: Custom metrics
5. **Features**: Batch processing, webhooks

## 🐛 Troubleshooting

### Common Issues

**Port already in use:**
```bash
docker-compose down
sudo lsof -i :8000  # Check what's using port
```

**HuggingFace token error:**
- Verify token in `.env`
- Accept model license on HuggingFace

**Out of memory:**
- Reduce `WHISPER_MODEL` to "small" or "base"
- Increase Docker memory limit

**Worker not processing:**
```bash
docker-compose logs worker
docker-compose restart worker
```

## 📄 License

MIT License

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Test thoroughly
5. Submit pull request

!!!
also workers / queues .. 

probably: https://github.com/rq/rq
authentication 


!!!
I need audio preprocessing where all audio is set to 16khz

!!!
ELK / Cloud Logging — логи API и воркеров.
Лимит хранения логов: 30 дней.


Endpoints I need:

POST /transcribe

curl -X POST "https://api.example.com/transcribe" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@meeting.mp3" \
  -F "lang=auto" \
  -F "model=large" \
  -F "format=json" \
  -F "diarization=true"

Ответ:

{
  "task_id": "1d3a6b2e-8c44-4f1b-9f3b-52dc8a1ff321",
  "status": "queued",
  "message": "Задача успешно создана"
}


GET /status/{task_id}

{
  "task_id": "1d3a6b2e-8c44-4f1b-9f3b-52dc8a1ff321",
  "status": "processing",
  "progress": 42,
  "eta_seconds": 75
}

GET /result/{task_id} (json формат)

{
  "task_id": "1d3a6b2e-8c44-4f1b-9f3b-52dc8a1ff321",
  "status": "done",
  "language": "en",
  "model": "large",
  "segments": [
    {
      "start": 0.0,
      "end": 4.5,
      "speaker": "spk_1",
      "text": "Hello everyone, welcome to the meeting."
    },
    {
      "start": 4.6,
      "end": 8.2,
      "speaker": "spk_2",
      "text": "Thanks, let’s get started with today’s agenda."
    }
  ]
}

MinIO for local S3 or just AWS s3...
tutorial : https://www.youtube.com/watch?v=zjpbPWUbkKI

https://hub.docker.com/r/minio/minio

docker run -p 9000:9000 -p 9001:9001 \
  quay.io/minio/minio server /data --console-address ":9001"


check out srt and vtt formats

https://jbilocalization.com/the-difference-between-srt-and-webvtt-in-captioning-subtitling/





For rate limiting I want to use caddy-ratelimit!

 also i can make use of 
from starlette.middleware.base import BaseHTTPMiddleware , so i can have 2 
layers of rate limiting , outermost is against ddos and inner is for business logic 

For now i only need caddy layer 



        allowed_models = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"] #also turbo


        worker concurrency vs max task concurrency? 

        check if we clean files properly, make sure there are no edge cases


        if url_type == 'youtube':
            base_opts.update({
                'format': 'best[height<=720]/best',  # I don;'t need high quality of video, i only seek audio
                'writesubtitles': False,
                'writeautomaticsub': False,
            })


      how useful _get_ydl_options, maybe just maxfile size is all i need....

        domain = parsed.netloc.lower() - check how works


        we anyway give options such that no need in :
              filesize = info.get('filesize') or info.get('filesize_approx')
                    if filesize and filesize > self.max_file_size:
                        raise Exception(f"File too large: {filesize/1024/1024:.1f}MB (max: {self.max_file_size/1024/1024:.1f}MB)")
                    

              and   if duration > settings.max_duration_seconds:
                await task_manager.update_task_status(
                    task_id, "error", 
                    error_message=f"Audio too long. Maximum duration: {settings.max_duration_hours} hours ({duration/3600:.1f} hours provided)"
                )


       output_template = os.path.join(temp_dir, f"{task_id}_%(title)s.%(ext)s") - title and ext ? 



       downloaded_file.unlink() - unlink ? 


       async def download_audio_from_url(url: str, task_id: str) -> str:
    """Download audio file from URL using yt-dlp for better support"""
    try:
        # Use the URL downloader service for comprehensive URL support
        file_path, original_filename = await url_downloader.download_from_url(
            url=url,
            task_id=task_id,
            upload_dir=settings.upload_dir
        )
        
        # Convert to 16kHz WAV for optimal Whisper processing
        wav_path = await convert_audio_to_wav_16khz(file_path)
        
        # Remove original file if conversion was successful and different
        if wav_path != file_path:
            os.remove(file_path)
        
        return wav_path
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download audio: {str(e)}")

        - should be put to a separate from transcription file place


    I need to store hitory of transcripts by api key in postgresql
    
