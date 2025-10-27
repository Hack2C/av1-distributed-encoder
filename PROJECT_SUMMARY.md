# Project Overview

**AV1 Media Transcoding System** - Complete implementation with 18 features

## ✅ Completed Features

### Core Functionality
1. ✅ **Quality Lookup Tables** - Adjusted CRF values (reduced by 3-4 points) for better perceptual quality with AV1
2. ✅ **Project Structure** - config.json, web/, lib/ directories, all organized
3. ✅ **SQLite Database** - Complete state management with resume capability
4. ✅ **Media Scanner** - Recursive scanning of Movies/, TV/, TestLib/
5. ✅ **FFprobe Integration** - Extracts all metadata (codec, bitrate, HDR, audio)
6. ✅ **Quality Lookup Logic** - Maps source → optimal CRF & Opus bitrate
7. ✅ **Transcoding Engine** - Full workflow with .av1.inprogress markers
8. ✅ **Safe File Replacement** - Atomic operations with .bak files
9. ✅ **Process Priority** - nice + ionice for low-priority operation
10. ✅ **Error Handling** - NAS disconnection, app shutdown, resume support
11. ✅ **Disk Space Tracking** - Real-time savings calculation & estimation
12. ✅ **Flask REST API** - /api/status, /api/files, /api/pause, etc.
13. ✅ **Web Interface** - Beautiful dashboard with real-time stats
14. ✅ **WebSocket Updates** - Live progress via Socket.IO
15. ✅ **Output Verification** - Checks file validity before replacement
16. ✅ **Comprehensive Logging** - File + console logging
17. ✅ **Testing Mode** - Keeps .bak files when enabled
18. ✅ **Documentation** - README.md with full instructions

## 📁 File Structure

```
/home/wieczorek/av1/
├── transcode.py              # Main entry point
├── config.json               # Configuration
├── requirements.txt          # Python dependencies
├── README.md                 # Documentation
├── install.sh                # Installation script
├── quality_lookup.json       # Video CRF lookup (ADJUSTED)
├── audio_codec_lookup.json   # Audio Opus bitrate lookup
├── lib/
│   ├── __init__.py
│   ├── config.py            # Config management
│   ├── database.py          # SQLite state management
│   ├── scanner.py           # Media file scanner
│   ├── probe.py             # FFprobe wrapper
│   ├── quality.py           # Quality settings lookup
│   ├── transcoder.py        # Core transcoding engine
│   └── web_api.py           # Flask REST API
└── web/
    ├── index.html           # Web dashboard
    ├── style.css            # Styling
    └── app.js               # Frontend JavaScript

Media Directories:
├── Movies/                   # Configured in config.json
├── TV/                       # Configured in config.json
└── TestLib/                  # Configured in config.json
```

## 🚀 Usage

### Installation
```bash
chmod +x install.sh
./install.sh
```

### Configuration
Edit `config.json`:
- Set your media directories
- Set temp directory (needs space for 1 file)
- Keep `testing_mode: true` initially

### Run
```bash
python3 transcode.py
```

### Web Interface
Open browser: `http://localhost:8080`

## 🎯 Key Improvements Made

### Quality Settings
- **Reduced CRF values by 3-4 points** across all codecs for perceptually lossless quality
- H.264 1080p 8Mbps: CRF 26 → **22** (better quality)
- HEVC 4K 10Mbps: CRF 27 → **23** (better quality)
- Default values also lowered for safety

### Workflow
1. Scans media directories
2. Creates `.av1.inprogress` marker
3. Copies to temp (protects NAS)
4. Probes metadata
5. Looks up optimal settings
6. Transcodes with SVT-AV1 preset 0 + Opus
7. Verifies output
8. Safely replaces original
9. Deletes .bak (unless testing mode)

### Safety
- Testing mode keeps backups
- Atomic file operations
- NAS disconnect handling
- Resume from last checkpoint
- Low priority (nice 19, ionice class 3)

## 📊 Web Dashboard Features

- **Real-time stats**: Total files, completed, pending, failed
- **Disk savings**: Original size, current size, savings (GB & %)
- **Estimates**: Predicted final size based on actual compression
- **Current file**: Live progress bar with codec info
- **Controls**: Pause, Resume, Rescan
- **File list**: Sortable, filterable table
- **Live updates**: WebSocket for instant feedback

## ⚙️ Technical Details

- **Python 3** with Flask + Flask-SocketIO
- **SQLite** for persistence
- **FFmpeg** with libsvtav1 + libopus
- **Process priority**: nice + ionice
- **Error recovery**: Database state tracking
- **Web**: Simple HTML/CSS/JS (no frameworks)

## 🔧 Next Steps for User

1. **Install dependencies**: Run `./install.sh`
2. **Edit config.json**: Set your actual media paths
3. **Test on one file**: Keep testing_mode=true
4. **Review .bak file**: Verify quality is acceptable
5. **Set testing_mode=false**: When confident
6. **Monitor**: Use web interface at :8080

## 💡 Tips

- Start with a small test library first
- SVT-AV1 preset 0 is VERY slow but highest quality
- Typical compression: 40-50% from H.264, 20-30% from HEVC
- Keep enough temp space for your largest file
- Monitor the first few files closely
