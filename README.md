# AV1 Distributed Transcoding System

Automated media library transcoding to AV1 (SVT-AV1) with Opus audio. Supports both standalone single-machine processing and distributed multi-machine parallel processing for maximum efficiency.

## Features

### Core Functionality
- ✅ **AV1 Encoding**: SVT-AV1 preset 0 for maximum compression efficiency
- ✅ **Opus Audio**: High-quality audio with excellent compression
- ✅ **Quality-Aware**: Automatic CRF selection based on source bitrate/resolution/codec
- ✅ **Web Interface**: Real-time monitoring with progress tracking
- ✅ **Safe Processing**: Testing mode, backup files, atomic operations
- ✅ **Smart Verification**: Only replaces files with 5%+ savings

### Distribution Features
- ✅ **Master/Worker Architecture**: Coordinate jobs across multiple computers
- ✅ **Automatic Job Distribution**: Workers request jobs when idle
- ✅ **Real-time Monitoring**: Single web UI shows all workers and progress
- ✅ **Health Monitoring**: Auto-detect worker failures with 30s timeout
- ✅ **Scalable**: Add workers dynamically for linear performance scaling

## Quick Start

### Docker (Recommended - Works on Windows, Linux, Mac)

**Master Server (Linux):**
```bash
docker-compose -f docker-compose.master.yml up -d
# Access at http://localhost:8090
```

**Worker (Windows/Linux/Mac):**
1. Install Docker Desktop
2. Edit `docker-compose.worker.yml`:
   - Set media paths (e.g., `D:/Movies:/media/Movies`)
   - Change `MASTER_IP` to your master server's IP
3. Run:
```bash
docker-compose -f docker-compose.worker.yml up -d
```

Or on Windows, double-click `start-worker.bat`

### Native Python (Linux/Mac)

**Standalone Mode:**
```bash
python3 transcode.py
# Access at http://localhost:8090
```

**Distributed Mode:**

Master Server:
```bash
./start_master.sh
# Access at http://localhost:8090
```

Worker:
```bash
./start_worker.sh http://MASTER_IP:8090
```

Replace `MASTER_IP` with your master server's IP address.

## Installation

### Docker (Recommended)

**Prerequisites:**
- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Access to media files (local or network share)

**Setup:**

1. **Clone/Download this repository**

2. **For Master Server (Linux):**
   ```bash
   # Edit docker-compose.master.yml - set your media paths
   nano docker-compose.master.yml
   
   # Build and start
   docker-compose -f docker-compose.master.yml up -d
   
   # View logs
   docker-compose -f docker-compose.master.yml logs -f
   ```

3. **For Worker (Windows):**
   ```powershell
   # Edit docker-compose.worker.yml
   # - Set media paths: D:/Movies:/media/Movies
   # - Set MASTER_IP in command line
   notepad docker-compose.worker.yml
   
   # Run
   docker-compose -f docker-compose.worker.yml up -d
   
   # Or double-click start-worker.bat
   ```

**Docker Configuration:**

The Docker setup uses `config.docker.json` with container paths:
```json
{
  "media_directories": [
    "/media/Movies",
    "/media/TV"
  ],
  "temp_directory": "/tmp/av1_transcoding",
  "testing_mode": true,
  "web_port": 8090
}
```

You map your actual media directories in `docker-compose.yml`:
```yaml
volumes:
  - /your/actual/Movies:/media/Movies
  - D:/TV:/media/TV  # Windows example
```

### Native Python (Linux/Mac)

**System Dependencies:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ffmpeg python3 python3-pip

# Verify FFmpeg has required encoders
ffmpeg -encoders | grep -E "libsvtav1|libopus"
```

**Python Dependencies:**
```bash
pip3 install -r requirements.txt
```

**Configuration:**

Edit `config.json`:
```json
{
  "media_directories": [
    "/path/to/Movies",
    "/path/to/TV"
  ],
  "temp_directory": "/tmp/av1_transcoding",
  "web_port": 8090,
  "testing_mode": true
}
```

**Important Settings:**
- `media_directories`: Your media folders to scan
- `testing_mode: true`: Keep `.bak` files for safety (recommended initially)
- `testing_mode: false`: Auto-delete backups after successful transcode

## Architecture

### Standalone Mode
```
┌─────────────────────┐
│   Single Computer   │
│  • Scan media       │
│  • Queue files      │
│  • Transcode 1-by-1 │
│  • Web UI           │
└─────────────────────┘
```

### Distributed Mode
```
┌─────────────────────────────────────────┐
│    Master Server (Port 8090)            │
│  • Job coordination                     │
│  • Worker management                    │
│  • Unified web UI                       │
│  • Progress aggregation                 │
└──────────────┬──────────────────────────┘
               │
   ┌───────────┴───────────┬──────────────┐
   │                       │              │
┌──▼────┐             ┌───▼────┐    ┌───▼────┐
│Worker1│             │Worker 2│    │Worker 3│
│Transcode│           │Transcode│  │Transcode│
└───────┘             └────────┘    └────────┘
```

## How It Works

### Processing Pipeline
1. **Scan**: Media directories scanned for video files
2. **Queue**: Files added to SQLite database queue
3. **Analyze**: FFmpeg probes metadata (codec, bitrate, resolution, HDR)
4. **Lookup**: Quality tables determine optimal CRF and audio bitrate
5. **Transcode**: SVT-AV1 + Opus encoding in temp directory
6. **Verify**: Check output size (must save 5%+ to replace)
7. **Replace**: Atomic replacement with backup (.bak)
8. **Cleanup**: Delete backup (unless testing mode)

### Quality Optimization

**Video Encoding:**
- Dynamic CRF based on source resolution and bitrate
- HDR support with automatic detection
- Pixel-based resolution classification (handles ultra-wide)

**Audio Encoding:**
- Channel-aware Opus bitrate selection
- Preserves all audio tracks and subtitles
- Maintains metadata

Quality lookup tables in `quality_lookup.json` and `audio_codec_lookup.json`.

## Distributed System

### Master Server
- Coordinates all transcoding work
- Manages worker registration and health
- Distributes jobs to available workers
- Provides unified web interface at http://MASTER_IP:8090
- Auto-detects worker failures (30s timeout)
- Reassigns failed jobs automatically

### Worker Client
- Connects to master server
- Reports system capabilities (CPU, memory)
- Requests jobs when idle
- Transcodes files locally
- Reports real-time progress
- Sends heartbeat every 10 seconds

### Network Requirements
- Workers need HTTP/WebSocket access to master (port 8090)
- All machines need read/write access to media files (shared NAS)
- Firewall must allow master server port

### Performance Scaling
- **1 worker**: ~1 file at a time (same as standalone)
- **3 workers**: ~3 files in parallel (3x faster)
- **N workers**: ~N files in parallel (N× faster)

Example: 100 files × 30 min/file
- Standalone: 50 hours
- 3 workers: ~17 hours
- 5 workers: ~10 hours

## Web Interface

### Standalone Mode (`http://localhost:8090`)
- Current file being processed
- Progress bar with speed/ETA
- Queue status (pending/processing/completed/failed)
- Overall statistics and savings
- File management (reset, skip, delete, abort, retry)

### Distributed Mode (`http://MASTER_IP:8090`)
- **Worker Cards**: Status, CPU/memory, jobs completed/failed
- **Job Queue**: All files with worker assignments
- **Statistics**: Overall progress across all workers
- **Real-time Updates**: WebSocket + auto-refresh

## File Management

### Database Actions (Web UI)
- **Reset**: Move failed file back to pending
- **Skip**: Mark file as completed without processing
- **Delete**: Remove file from queue
- **Abort**: Stop currently processing file
- **Retry**: Restart stuck processing file

### Command Line Utilities
```bash
# Reset all failed files
python3 reset_failed.py

# Manage queue
python3 manage_queue.py
```

## Safety Features

### Data Protection
- **Testing Mode**: Keeps `.bak` files for manual verification
- **Atomic Operations**: Uses temp files to avoid corruption
- **5% Minimum Savings**: Won't replace if output isn't smaller enough
- **Backup Files**: Original saved as `.bak` (deleted in production mode)

### Reliability
- **Resume Support**: Continues from last checkpoint after interruption
- **Worker Failover**: Master reassigns jobs from disconnected workers
- **Progress Persistence**: SQLite database survives restarts
- **Graceful Shutdown**: Signal handlers for clean exit

## Troubleshooting

### Standalone Issues
```bash
# Check if service is running
ps aux | grep transcode.py

# View logs
tail -f /tmp/av1_transcoding.log  # if configured

# Test encoding
ffmpeg -i test.mkv -c:v libsvtav1 -crf 30 -c:a libopus -b:a 128k test_av1.mkv
```

### Distributed Issues

**Worker won't connect:**
```bash
# Check master is accessible
curl http://MASTER_IP:8090/api/status

# Check firewall
sudo ufw status
sudo ufw allow 8090/tcp
```

**Jobs not being assigned:**
- Verify workers show as "idle" in web UI
- Check media directories accessible from workers
- Review master server logs
- Ensure files are in "pending" status

**Progress not updating:**
- Check browser console for WebSocket errors
- Verify no proxy blocking WebSocket connection
- Try refreshing page (auto-refresh every 5s)

## Project Structure

```
av1/
├── transcode.py              # Standalone server
├── master_server.py          # Master coordination server
├── worker_client.py          # Worker processing client
├── config.json               # Configuration
├── quality_lookup.json       # Video quality settings
├── audio_codec_lookup.json   # Audio quality settings
├── requirements.txt          # Python dependencies
├── start_master.sh           # Master startup script
├── start_worker.sh           # Worker startup script
├── lib/
│   ├── config.py            # Configuration management
│   ├── database.py          # SQLite queue management
│   ├── scanner.py           # Media directory scanner
│   ├── probe.py             # FFmpeg metadata probing
│   ├── quality.py           # Quality lookup logic
│   ├── transcoder.py        # Transcoding engine
│   ├── web_api.py           # Flask API routes
│   └── master_coordinator.py # Worker management
└── web/
    ├── index.html           # Standalone web UI
    ├── master.html          # Distributed web UI
    ├── app.js              # Standalone JavaScript
    ├── master.js           # Distributed JavaScript
    └── style.css           # Shared styles
```

## License

MIT
