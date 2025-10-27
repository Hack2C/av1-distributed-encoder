#!/usr/bin/env python3
"""
Quick test script to verify the setup without starting the full service
"""

import sys
import json
import subprocess
from pathlib import Path

def test_dependencies():
    """Test if all required dependencies are available"""
    print("🔍 Testing Dependencies")
    print("=" * 50)
    
    tests = []
    
    # Test Python modules
    print("\n📦 Python Modules:")
    for module in ['flask', 'flask_socketio', 'flask_cors']:
        try:
            __import__(module)
            print(f"  ✅ {module}")
            tests.append(True)
        except ImportError:
            print(f"  ❌ {module} - Run: pip3 install -r requirements.txt")
            tests.append(False)
    
    # Test FFmpeg
    print("\n🎬 Media Tools:")
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f"  ✅ ffmpeg")
            tests.append(True)
        else:
            print(f"  ❌ ffmpeg - Install with: sudo apt-get install ffmpeg")
            tests.append(False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"  ❌ ffmpeg - Install with: sudo apt-get install ffmpeg")
        tests.append(False)
    
    # Test FFprobe
    try:
        result = subprocess.run(['ffprobe', '-version'], 
                              capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f"  ✅ ffprobe")
            tests.append(True)
        else:
            print(f"  ❌ ffprobe")
            tests.append(False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"  ❌ ffprobe")
        tests.append(False)
    
    # Test SVT-AV1
    try:
        result = subprocess.run(['ffmpeg', '-codecs'], 
                              capture_output=True, text=True, timeout=5)
        if 'libsvtav1' in result.stdout:
            print(f"  ✅ libsvtav1 (SVT-AV1 encoder)")
            tests.append(True)
        else:
            print(f"  ⚠️  libsvtav1 - May need to install SVT-AV1")
            print(f"     Check: https://gitlab.com/AOMediaCodec/SVT-AV1")
            tests.append(False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"  ❌ Cannot check for libsvtav1")
        tests.append(False)
    
    # Test Opus
    try:
        result = subprocess.run(['ffmpeg', '-codecs'], 
                              capture_output=True, text=True, timeout=5)
        if 'libopus' in result.stdout:
            print(f"  ✅ libopus (Opus encoder)")
            tests.append(True)
        else:
            print(f"  ⚠️  libopus - May need libopus support in ffmpeg")
            tests.append(False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"  ❌ Cannot check for libopus")
        tests.append(False)
    
    return all(tests)

def test_config():
    """Test configuration file"""
    print("\n⚙️  Configuration:")
    
    if not Path('config.json').exists():
        print("  ❌ config.json not found")
        return False
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        print("  ✅ config.json is valid JSON")
        
        # Check source directories
        dirs = config.get('source_directories', [])
        print(f"\n  📁 Source Directories ({len(dirs)}):")
        for d in dirs:
            path = Path(d)
            if path.exists():
                print(f"    ✅ {d}")
            else:
                print(f"    ⚠️  {d} (does not exist)")
        
        # Check temp directory
        temp = config.get('temp_directory', '/tmp/av1_transcoding')
        temp_path = Path(temp)
        if temp_path.exists():
            print(f"\n  ✅ Temp directory: {temp}")
        else:
            print(f"\n  ⚠️  Temp directory will be created: {temp}")
        
        # Check testing mode
        testing = config.get('testing_mode', True)
        print(f"\n  {'🧪' if testing else '⚡'} Testing mode: {testing}")
        if testing:
            print("    (Backup files will be kept)")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"  ❌ config.json is invalid: {e}")
        return False

def test_lookups():
    """Test lookup files"""
    print("\n📊 Lookup Tables:")
    
    tests = []
    
    for filename in ['quality_lookup.json', 'audio_codec_lookup.json']:
        if not Path(filename).exists():
            print(f"  ❌ {filename} not found")
            tests.append(False)
            continue
        
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            print(f"  ✅ {filename}")
            tests.append(True)
        except json.JSONDecodeError as e:
            print(f"  ❌ {filename} is invalid: {e}")
            tests.append(False)
    
    return all(tests)

def main():
    """Run all tests"""
    print("\n" + "=" * 50)
    print("🎬 AV1 Transcoding Service - Setup Test")
    print("=" * 50)
    
    results = []
    
    results.append(test_dependencies())
    results.append(test_config())
    results.append(test_lookups())
    
    print("\n" + "=" * 50)
    if all(results):
        print("✅ All tests passed! Ready to run.")
        print("\nStart the service with:")
        print("  python3 transcode.py")
        print("\nThen open: http://localhost:8080")
        return 0
    else:
        print("⚠️  Some tests failed. Please fix the issues above.")
        print("\nRun the installation script:")
        print("  ./install.sh")
        return 1

if __name__ == '__main__':
    sys.exit(main())
