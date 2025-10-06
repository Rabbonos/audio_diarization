#!/bin/bash

# GPU Setup Verification Script for Audio Diarization

echo "🔍 Checking GPU setup for Whisper model..."

echo ""
echo "1️⃣ Checking NVIDIA drivers..."
if command -v nvidia-smi &> /dev/null; then
    echo "✅ NVIDIA drivers installed"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
    echo "❌ NVIDIA drivers not found"
    echo "   Install: sudo apt install nvidia-driver-xxx"
fi

echo ""
echo "2️⃣ Checking Docker..."
if command -v docker &> /dev/null; then
    echo "✅ Docker installed"
    docker --version
else
    echo "❌ Docker not found"
fi

echo ""
echo "3️⃣ Checking NVIDIA Container Toolkit..."
if docker info | grep -q nvidia; then
    echo "✅ NVIDIA Container Toolkit configured"
    echo "   Docker runtime: nvidia"
else
    echo "❌ NVIDIA Container Toolkit not configured"
    echo "   Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    echo "   Commands:"
    echo "     distribution=\$(. /etc/os-release;echo \$ID\$VERSION_ID)"
    echo "     curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -"
    echo "     curl -s -L https://nvidia.github.io/libnvidia-container/\$distribution/libnvidia-container.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list"
    echo "     sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit"
    echo "     sudo systemctl restart docker"
fi

echo ""
echo "4️⃣ Checking Docker Compose syntax..."
if docker-compose config > /dev/null 2>&1; then
    echo "✅ docker-compose.yaml syntax valid"
else
    echo "❌ docker-compose.yaml has syntax errors"
    docker-compose config
fi

echo ""
echo "5️⃣ Testing GPU access in container..."
echo "   Run this to test GPU access:"
echo "   docker run --rm --runtime=nvidia --gpus all nvidia/cuda:11.0-base nvidia-smi"

echo ""
echo "🚀 If all checks pass, your containers will have GPU access for Whisper!"
echo ""
echo "📊 Containers with GPU access:"
echo "   • app (FastAPI server)"
echo "   • rq_worker (background processing)"  
echo "   • nvidia-gpu-exporter (monitoring)"