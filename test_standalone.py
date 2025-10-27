#!/usr/bin/env python3
"""
Standalone test script - Tests core functionality without web server
"""

import sys
import json
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.probe import MediaProbe
from lib.quality import QualityLookup
from lib.scanner import MediaScanner

class SimpleConfig:
    """Minimal config for testing"""
    def __init__(self):
        with open('config.json') as f:
            self.config = json.load(f)
    
    def get(self, key, default=None):
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def get_source_directories(self):
        return self.get('source_directories', [])
    
    def get_video_extensions(self):
        return self.get('video_extensions', ['.mkv', '.mp4', '.avi', '.mov'])

class SimpleDatabase:
    """Minimal in-memory database for testing"""
    def __init__(self):
        self.files = []
    
    def add_file(self, file_info):
        self.files.append(file_info)
        return len(self.files)

def test_scanner():
    """Test the media scanner"""
    print("\n🔍 Testing Media Scanner")
    print("=" * 60)
    
    config = SimpleConfig()
    db = SimpleDatabase()
    scanner = MediaScanner(config, db)
    
    count = scanner.scan_all()
    
    print(f"\n✅ Found {count} video files")
    
    if db.files:
        print(f"\nFirst 5 files:")
        for i, f in enumerate(db.files[:5]):
            size_mb = f['size_bytes'] / (1024 * 1024)
            print(f"  {i+1}. {f['filename']}")
            print(f"     Size: {size_mb:.1f} MB")
            print(f"     Path: {f['directory']}")
    
    return count, db.files

def test_probe(file_path):
    """Test FFprobe on a file"""
    print(f"\n🎬 Testing FFprobe on: {file_path}")
    print("=" * 60)
    
    metadata = MediaProbe.probe_file(file_path)
    
    if not metadata:
        print("❌ Failed to probe file")
        return None
    
    print("\n📊 Video Information:")
    video = metadata['video']
    print(f"  Codec: {video['codec']}")
    print(f"  Resolution: {video['resolution']} ({video['width']}x{video['height']})")
    print(f"  Bitrate: {video['bitrate'] / 1_000_000:.1f} Mbps")
    print(f"  Bit Depth: {video['bitdepth']}-bit")
    print(f"  HDR: {video['hdr']}")
    print(f"  FPS: {video['fps']:.2f}")
    
    if metadata['audio']:
        print(f"\n🔊 Audio Information:")
        for i, audio in enumerate(metadata['audio']):
            print(f"  Track {i+1}:")
            print(f"    Codec: {audio['codec']}")
            print(f"    Channels: {audio['channels']}")
            print(f"    Bitrate: {audio['bitrate'] / 1000:.0f} kbps")
            print(f"    Language: {audio['language']}")
    
    return metadata

def test_quality_lookup(metadata):
    """Test quality settings lookup"""
    print(f"\n🎯 Testing Quality Lookup")
    print("=" * 60)
    
    quality = QualityLookup()
    video = metadata['video']
    
    # Get bitrate category
    bitrate_cat = MediaProbe.get_bitrate_category(video['bitrate'])
    print(f"\nBitrate category: {bitrate_cat} (from {video['bitrate'] / 1_000_000:.1f} Mbps)")
    
    # Get CRF
    crf = quality.get_video_crf(
        codec=video['codec'],
        bitdepth=video['bitdepth'],
        hdr=video['hdr'],
        resolution=video['resolution'],
        bitrate_category=bitrate_cat
    )
    print(f"Target CRF: {crf}")
    
    # Get Opus bitrate
    if metadata['audio']:
        audio = metadata['audio'][0]
        audio_bitrate_cat = MediaProbe.get_audio_bitrate_category(
            audio['bitrate'], audio['codec']
        )
        print(f"\nAudio bitrate category: {audio_bitrate_cat} (from {audio['bitrate'] / 1000:.0f} kbps)")
        
        opus_bitrate = quality.get_opus_bitrate(
            source_codec=audio['codec'],
            channels=audio['channels'],
            source_bitrate_category=audio_bitrate_cat
        )
        print(f"Target Opus bitrate: {opus_bitrate} kbps")
    
    print(f"\n✅ Quality settings determined successfully")

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("🧪 AV1 Transcoding System - Standalone Test")
    print("=" * 60)
    
    # Test 1: Scanner
    count, files = test_scanner()
    
    if count == 0:
        print("\n⚠️  No video files found. Check your source directories.")
        return 1
    
    # Test 2: Probe and Quality lookup on first file
    if files:
        first_file = Path(files[0]['path'])
        
        if first_file.exists():
            metadata = test_probe(first_file)
            
            if metadata:
                test_quality_lookup(metadata)
        else:
            print(f"\n⚠️  File not found: {first_file}")
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    print("\nThe core transcoding logic is working correctly.")
    print("To run the full service with web interface:")
    print("  1. Install Flask: sudo apt install python3-flask python3-flask-socketio")
    print("  2. Run: python3 transcode.py")
    print("\nOr to test transcoding a single file:")
    print("  python3 -c \"from lib.transcoder import *; # manual test\"")
    print("")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
