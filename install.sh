#!/bin/bash

# AV1 Transcoding Service - Installation Script
# For Ubuntu/Debian systems

echo "🎬 AV1 Transcoding Service Installation"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  This script should be run with sudo for system package installation"
    echo "Continuing anyway..."
fi

# Update package list
echo "📦 Updating package list..."
sudo apt-get update

# Install FFmpeg
echo "📦 Installing FFmpeg..."
sudo apt-get install -y ffmpeg

# Check if SVT-AV1 is available
echo "📦 Checking for SVT-AV1..."
if command -v SvtAv1EncApp &> /dev/null; then
    echo "✅ SVT-AV1 already installed"
else
    echo "⚠️  SVT-AV1 not found in system packages"
    echo "Please install SVT-AV1 manually from:"
    echo "  https://gitlab.com/AOMediaCodec/SVT-AV1"
    echo ""
    echo "Or check if your ffmpeg includes libsvtav1:"
    ffmpeg -codecs 2>/dev/null | grep -i svtav1 || echo "  libsvtav1 not found in ffmpeg"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Create temp directory
echo "📁 Creating temporary directory..."
mkdir -p /tmp/av1_transcoding

# Make script executable
chmod +x transcode.py

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.json to set your media directories"
echo "2. Review quality_lookup.json and audio_codec_lookup.json"
echo "3. Run: python3 transcode.py"
echo "4. Open browser to: http://localhost:8080"
echo ""
echo "⚠️  Important: Start with testing_mode=true in config.json!"
echo ""
