#!/usr/bin/env python3
"""
Simple debug script to test API endpoints
"""
import requests
import time
import os

BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("API_KEY", "mvp-api-key-123")
AUDIO_FILE = "sample.mp3"

print("🔍 Testing API Endpoints\n")

# 1. Health check
print("1️⃣ Testing /api/v1/system/health")
response = requests.get(f"{BASE_URL}/api/v1/system/health")
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}\n")

# 2. System stats
print("2️⃣ Testing /api/v1/system/stats")
response = requests.get(f"{BASE_URL}/api/v1/system/stats")
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}\n")

# 3. Transcribe audio
if os.path.exists(AUDIO_FILE):
    print(f"3️⃣ Testing /api/v1/transcribe with {AUDIO_FILE}")
    with open(AUDIO_FILE, "rb") as f:
        files = {"file": (AUDIO_FILE, f, "audio/mpeg")}
        headers = {"Authorization": f"Bearer {API_KEY}"}
        data = {"lang": "auto", "format": "json"}
        response = requests.post(f"{BASE_URL}/api/v1/transcribe", files=files, headers=headers, data=data)
    
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}\n")
    
    if response.status_code == 200:
        task_id = response.json().get("task_id")
        
        # 4. Check status
        print(f"4️⃣ Testing /api/v1/status/{task_id}")
        time.sleep(2)
        headers = {"Authorization": f"Bearer {API_KEY}"}
        response = requests.get(f"{BASE_URL}/api/v1/status/{task_id}", headers=headers)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")
        
        # 5. Wait for completion and get result
        if response.status_code == 200:
            status = response.json().get("status")
            print(f"5️⃣ Waiting for transcription to complete...")
            
            for i in range(60):  # Wait up to 60 seconds
                response = requests.get(f"{BASE_URL}/api/v1/status/{task_id}", headers=headers)
                if response.status_code == 200:
                    status = response.json().get("status")
                    progress = response.json().get("progress", 0)
                    print(f"   Status: {status}, Progress: {progress}%")
                    
                    if status in ["completed", "failed"]:
                        break
                time.sleep(1)
            
            if status == "completed":
                print(f"\n6️⃣ Getting transcription result...")
                response = requests.get(f"{BASE_URL}/api/v1/result/{task_id}", headers=headers)
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    result = response.json()
                    print(f"   Transcription text: {result.get('transcription_text', 'N/A')[:200]}...")
                else:
                    print(f"   Response: {response.json()}\n")
else:
    print(f"⚠️  Audio file '{AUDIO_FILE}' not found, skipping transcription test\n")

print("✅ Done!")
