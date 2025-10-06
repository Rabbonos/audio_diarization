"""
Authentication utilities for the audio diarization service
"""
from fastapi import Header, HTTPException, Depends
from .config import settings

async def verify_api_key(authorization: str = Header(None)):
    """Simple API key verification for MVP"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    api_key = authorization.replace("Bearer ", "")
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key

# Dependency for FastAPI endpoints
ApiKeyDep = Depends(verify_api_key)