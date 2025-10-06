#!/bin/bash
# MinIO initialization script
# This script ensures the MinIO bucket is created and properly configured

echo "🚀 Initializing MinIO storage..."

# Wait for MinIO to be ready
echo "⏳ Waiting for MinIO to be ready..."
while ! curl -f http://minio:9000/minio/health/live > /dev/null 2>&1; do
    echo "   MinIO not ready yet, waiting..."
    sleep 5
done

echo "✅ MinIO is ready!"

# Install mc (MinIO client) if not present
if ! command -v mc &> /dev/null; then
    echo "📦 Installing MinIO client..."
    curl -o /usr/local/bin/mc https://dl.min.io/client/mc/release/linux-amd64/mc
    chmod +x /usr/local/bin/mc
fi

# Configure MinIO client
echo "🔧 Configuring MinIO client..."
mc alias set myminio http://minio:9000 minioadmin minioadmin

# Create bucket if it doesn't exist
echo "📁 Creating bucket 'audio-files'..."
mc mb myminio/audio-files --ignore-existing

# Set bucket policy to allow uploads
echo "🔒 Setting bucket policy..."
cat > /tmp/bucket-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": ["*"]
      },
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::audio-files/*"]
    },
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": ["*"]
      },
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::audio-files"]
    }
  ]
}
EOF

mc policy set-json /tmp/bucket-policy.json myminio/audio-files

echo "✅ MinIO initialization complete!"
echo "🌐 MinIO Console: http://localhost:9001 (admin/minioadmin)"
echo "🗄️ S3 API: http://localhost:9000"