# 🎬 AV1 Media Transcoding System - Complete Guide

## 📋 Overview

A complete, production-ready system for transcoding your entire media library to AV1 (using SVT-AV1) with Opus audio. Designed specifically for NAS environments with safety features, testing mode, and a beautiful web interface.

## ✨ Features

- ✅ **SVT-AV1 Preset 0** - Highest quality, slowest speed
- ✅ **Opus Audio** - Superior compression with transparency
- ✅ **Quality-Aware** - CRF selection based on source characteristics
- ✅ **Safe Operations** - Backup files, atomic replacements, testing mode
- ✅ **NAS-Friendly** - Low priority, handles disconnections, temp file workflow
- ✅ **Web Dashboard** - Real-time monitoring at http://localhost:8080
- ✅ **Resume Support** - Continues after crashes or shutdowns
- ✅ **Disk Space Tracking** - Live savings calculation and estimates

## 🚀 Quick Start

### 1. Installation

```bash
# Run the installation script
./install.sh

# Or manually install dependencies
sudo apt-get update
sudo apt-get install -y ffmpeg python3 python3-pip
pip3 install -r requirements.txt
```

### 2. Configuration

Edit `config.json` to match your setup:

```json
{
  "source_directories": [
    "/path/to/your/Movies",
    "/path/to/your/TV",
    "/path/to/your/TestLib"
  ],
  "temp_directory": "/tmp/av1_transcoding",
  "testing_mode": true  // KEEP THIS TRUE INITIALLY!
}
```

### 3. Test Setup

```bash
# Verify everything is configured correctly
python3 test_setup.py
```

### 4. Run

```bash
# Start the service
python3 transcode.py

# Open web interface
# http://localhost:8080
```

## 📊 Web Interface

Access the dashboard at `http://localhost:8080` to see:

- **Statistics**: Total files, completed, pending, failed
- **Disk Savings**: Real-time tracking with estimates
- **Current File**: Live progress with codec details
- **Controls**: Pause, Resume, Rescan library
- **File List**: All files with status and savings

## ⚙️ How It Works

### Workflow for Each File

1. **Scan** - Discovers all video files in configured directories
2. **Queue** - Adds to SQLite database for tracking
3. **Marker** - Creates `.av1.inprogress` file
4. **Copy** - Copies source to temp directory (protects NAS)
5. **Probe** - Analyzes video/audio metadata with ffprobe
6. **Lookup** - Determines optimal CRF and Opus bitrate
7. **Transcode** - Encodes with SVT-AV1 + Opus
8. **Verify** - Checks output is valid
9. **Replace** - Safely replaces original:
   - Copy transcoded file back to original location
   - Rename original to `.bak`
   - Rename transcoded to original name
   - Delete `.bak` (unless testing mode)
10. **Stats** - Updates database with savings

### Quality Selection

**Video CRF** is selected based on:
- Source codec (H.264, HEVC, VP9, etc.)
- Bit depth (8-bit or 10-bit)
- HDR vs SDR
- Resolution (720p, 1080p, 1440p, 4K)
- Source bitrate

**Audio Opus Bitrate** is selected based on:
- Source codec (AAC, AC3, DTS, etc.)
- Channel count (1, 2, 6, 8)
- Source bitrate

All values are in `quality_lookup.json` and `audio_codec_lookup.json` (pre-configured for perceptually lossless quality).

## 🛡️ Safety Features

### Testing Mode

**Always start with `testing_mode: true`!**

When enabled:
- Keeps all `.bak` files
- Allows you to verify quality before committing
- Compare original vs transcoded

To verify quality:
1. Let it process a few files
2. Compare original (.bak) with new file
3. If satisfied, set `testing_mode: false`
4. Old .bak files can be manually deleted

### Error Handling

- **NAS Disconnection**: Service pauses, resumes when reconnected
- **App Crash**: Database tracks state, resumes on restart
- **Transcode Failure**: File marked as failed, continues with next
- **Low Priority**: Uses nice/ionice to avoid system impact

### File Safety

- Atomic operations (copy → rename)
- Verification before replacement
- `.av1.inprogress` markers prevent double-processing
- Temp directory isolation

## 📈 Expected Results

### Compression Ratios

Based on typical content:

| Source Codec | Expected Savings |
|--------------|-----------------|
| H.264        | 40-50%          |
| HEVC/H.265   | 20-30%          |
| VP9          | 15-25%          |
| Already AV1  | Skip or minimal |

### Processing Speed

SVT-AV1 Preset 0 is VERY slow:
- 1080p movie: 8-24 hours (depends on CPU)
- 4K movie: 24-72 hours
- TV episode: 2-8 hours

**This is normal!** Preset 0 prioritizes quality over speed.

## 🔧 Configuration Options

### config.json Reference

```json
{
  "source_directories": ["..."],     // Paths to scan
  "temp_directory": "...",           // Temp storage location
  "testing_mode": true,              // Keep backups
  
  "process_priority": {
    "nice": 19,                      // CPU priority (19 = lowest)
    "ionice_class": 3                // IO priority (3 = idle)
  },
  
  "web_server": {
    "host": "0.0.0.0",               // Listen address
    "port": 8080                     // Web interface port
  },
  
  "video_extensions": [              // File types to process
    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"
  ],
  
  "transcoding": {
    "video_codec": "libsvtav1",      // AV1 encoder
    "svt_av1_preset": 0,             // 0-13 (0=slowest, best)
    "audio_codec": "libopus",        // Audio encoder
    "copy_subtitles": true,          // Keep subs
    "copy_metadata": true,           // Keep metadata
    "container": "mkv"               // Output container
  }
}
```

## 🎯 Quality Lookup Tables

### quality_lookup.json

Maps source characteristics to AV1 CRF values:

```json
{
  "h264": {
    "8bit": {
      "SDR": {
        "1080p": {
          "4M": 25,    // 4 Mbps source → CRF 25
          "8M": 22,    // 8 Mbps source → CRF 22
          // ...
        }
      }
    }
  }
}
```

**Lower CRF = Higher Quality** (range: 0-63)
- Adjusted 3-4 points lower than defaults for perceptual transparency

### audio_codec_lookup.json

Maps source audio to Opus bitrate:

```json
{
  "aac": {
    "2ch": {
      "128k": 80,    // 128k AAC stereo → 80k Opus
      "256k": 112    // 256k AAC stereo → 112k Opus
    }
  }
}
```

## 📁 File Structure

```
av1/
├── transcode.py              # Main application
├── config.json               # Your configuration
├── requirements.txt          # Python dependencies
├── install.sh                # Installation script
├── test_setup.py             # Setup verification
├── quality_lookup.json       # Video quality settings
├── audio_codec_lookup.json   # Audio quality settings
├── transcoding.db            # SQLite database (created on first run)
├── transcoding.log           # Log file (created on first run)
│
├── lib/                      # Python modules
│   ├── config.py
│   ├── database.py
│   ├── scanner.py
│   ├── probe.py
│   ├── quality.py
│   ├── transcoder.py
│   └── web_api.py
│
└── web/                      # Web interface
    ├── index.html
    ├── style.css
    └── app.js
```

## 🐛 Troubleshooting

### Service won't start

```bash
# Check dependencies
python3 test_setup.py

# Check logs
tail -f transcoding.log
```

### Files not being found

- Check `source_directories` in config.json
- Ensure paths are absolute
- Check NAS is mounted
- Try manual rescan from web interface

### Transcoding fails

- Check ffmpeg has libsvtav1: `ffmpeg -codecs | grep svtav1`
- Check temp directory has space
- Check source file is readable
- Review logs for specific errors

### Web interface not loading

- Check port 8080 is not in use
- Try accessing via IP: `http://YOUR_IP:8080`
- Check firewall settings

### Slow transcoding

This is normal! SVT-AV1 preset 0 is extremely slow.
- Consider preset 4-6 for faster encoding (edit config.json)
- Preset 6 is still high quality, much faster

## 💡 Pro Tips

1. **Start Small**: Test with a small library first
2. **Monitor First File**: Watch it complete and verify quality
3. **Check .bak Files**: Compare before deleting
4. **Disk Space**: Ensure temp directory has enough space for largest file
5. **Long Term**: Plan for days/weeks of processing time
6. **Remote Access**: Use SSH tunnel for remote monitoring
7. **Resume**: Service can be stopped/started safely

## 🔐 Security Notes

- Web interface has no authentication (use firewall/VPN for remote access)
- Runs on local network by default (0.0.0.0:8080)
- For production, consider adding authentication or restricting to 127.0.0.1

## 📞 Support

Check logs:
```bash
tail -f transcoding.log
```

Database status:
```bash
sqlite3 transcoding.db "SELECT status, COUNT(*) FROM files GROUP BY status;"
```

## 📄 License

MIT License - Use freely, modify as needed

---

**Ready to start?**

1. Run `./install.sh`
2. Edit `config.json`
3. Run `python3 test_setup.py`
4. Run `python3 transcode.py`
5. Open `http://localhost:8080`

**Remember: testing_mode=true for first runs!**
