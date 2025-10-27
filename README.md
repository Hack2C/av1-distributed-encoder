# 🎬 AV1 Distributed Transcoding System

High-performance distributed media transcoding system that converts your entire library to AV1 (SVT-AV1) with Opus audio. Features modern web interface, smart quality optimization, and distributed processing across multiple machines.

## ✨ Features

### Core Capabilities
- ✅ **AV1 Encoding** - SVT-AV1 with configurable presets (0-13)
- ✅ **Opus Audio** - High-quality audio with excellent compression
- ✅ **Smart Quality** - Automatic CRF/bitrate based on source resolution and codec
- ✅ **Modern Web UI** - Real-time monitoring with detailed progress tracking
- ✅ **Safe Processing** - Testing mode, backups, atomic file operations
- ✅ **Efficient** - Only replaces files with 5%+ space savings

### Distributed Processing
- ✅ **Master/Worker Architecture** - Coordinate jobs across multiple computers
- ✅ **Auto Job Distribution** - Workers request jobs when idle
- ✅ **Real-time Monitoring** - Single unified web interface
- ✅ **Health Monitoring** - Auto-detect and recover from worker failures
- ✅ **Linear Scaling** - Add workers for proportional speedup
- ✅ **File Distribution Mode** - HTTP-based transfers (no shared storage needed)

### Advanced Features
- ✅ **Job Controls** - Cancel, retry, skip, delete operations
- ✅ **Detailed Tracking** - Resolution, codec, bitrate, worker assignment
- ✅ **Time Estimates** - Per-file and overall ETA with processing speed
- ✅ **Process Priority** - Configurable nice/ionice for background operation
- ✅ **HDR Support** - Automatic detection and preservation
- ✅ **Multi-track** - Preserves all audio tracks, subtitles, and metadata

## 🚀 Quick Start

### Docker (Recommended)

**Master Server:**
```bash
# Create config directory
mkdir -p master-data/config

# Start master
docker compose -f docker-compose.master.yml up -d

# Access web UI
open http://localhost:8090
```

**Worker Node:**
```bash
# Copy worker config
cp docker-compose.worker.yml docker-compose.worker-1.yml

# Edit configuration (set MASTER_URL and media paths)
nano docker-compose.worker-1.yml

# Start worker
docker compose -f docker-compose.worker-1.yml up -d
```

### Native Python

**Standalone Mode:**
```bash
# Install dependencies
pip3 install -r requirements.txt

# Edit config.json
nano config.json

# Run
python3 transcode.py
```

**Distributed Mode:**
```bash
# Master
./start_master.sh

# Worker
./start_worker.sh http://MASTER_IP:8090
```

## 📦 Installation

### Prerequisites

**Docker Method:**
- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Access to media files (local or network share)

**Native Method:**
- Python 3.12+
- FFmpeg with libsvtav1 and libopus support

### Configuration

**Environment Variables:**
```bash
# Application
MEDIA_DIRS=/media/Movies,/media/TV        # Media directories (comma-separated)
TEMP_DIR=/tmp/av1_transcoding             # Temporary processing directory
WEB_PORT=8090                              # Web interface port
TESTING_MODE=true                          # Keep backup files for verification

# Master Connection (Workers Only)
MASTER_URL=http://192.168.1.100:8090      # Master server URL

# Encoding Settings
SVT_AV1_PRESET=8                          # 0-13 (0=slowest/best, 8=balanced, 13=fastest)

# Process Priority
NICE_LEVEL=19                              # CPU priority (0-19, 19=lowest)
IONICE_CLASS=3                             # I/O priority (1-3, 3=idle)

# File Distribution (Optional)
FILE_DISTRIBUTION_MODE=false               # true=HTTP transfer, false=shared storage

# Network Shares (Optional)
SMB_HOST=192.168.1.10                      # NAS hostname/IP
SMB_SHARE=Media                            # Share name
SMB_USERNAME=user                          # Username
SMB_PASSWORD=password                      # Password
SMB_VERSION=3.0                            # SMB protocol version
```

## 🏗️ Architecture

### System Overview

```
┌─────────────────────────────────────────┐
│         Master Server (8090)            │
│  • Job coordination & queue management  │
│  • Worker health monitoring             │
│  • Modern web interface                 │
│  • Progress aggregation                 │
│  • File distribution (optional)         │
└──────────────┬──────────────────────────┘
               │
   ┌───────────┴───────────┬──────────────┐
   │                       │              │
┌──▼────────┐      ┌──────▼─────┐   ┌───▼────────┐
│  Worker 1  │      │  Worker 2  │   │  Worker 3  │
│ Transcode  │      │ Transcode  │   │ Transcode  │
│ Progress   │      │ Progress   │   │ Progress   │
│ Heartbeat  │      │ Heartbeat  │   │ Heartbeat  │
└────────────┘      └────────────┘   └────────────┘
```

### Processing Pipeline

1. **Scan** - Master scans media directories for video files
2. **Queue** - Files added to SQLite database with metadata
3. **Probe** - FFmpeg analyzes source (codec, resolution, HDR, audio)
4. **Assign** - Master assigns job to idle worker
5. **Transfer** (File Distribution Mode) - Master sends file to worker via HTTP
6. **Transcode** - Worker encodes with SVT-AV1 + Opus
7. **Upload** (File Distribution Mode) - Worker sends result back to master
8. **Verify** - Check quality and size savings (minimum 5%)
9. **Replace** - Atomic file replacement with backup
10. **Cleanup** - Delete backup if not in testing mode

### Operating Modes

#### Shared Storage Mode (Default)
```yaml
FILE_DISTRIBUTION_MODE=false
```
- All machines access files via network shares (SMB/NFS)
- Faster for local networks
- Requires shared storage setup
- Recommended for LAN deployments

#### File Distribution Mode
```yaml
FILE_DISTRIBUTION_MODE=true
```
- Master transfers files to workers via HTTP
- No shared storage needed
- Works across different networks
- Ideal for remote workers or simplified setup

## 🎨 Web Interface

### Modern Dashboard

Access at `http://MASTER_IP:8090`

**Statistics Overview:**
- Total files, pending, processing, completed
- Space saved across library
- Estimated time remaining

**Worker Cards:**
- Status (idle/processing/offline)
- CPU and memory usage
- Current file with progress bar
- Processing speed (FPS) and ETA
- Completed/failed job counts

**File Queue:**
- Detailed file information (resolution, codec, size)
- Status badges with color coding
- Real-time progress bars
- Job controls (cancel, retry, skip, delete)
- Filter by status
- Search by filename

**Job Controls:**
- **Cancel** - Stop processing file
- **Retry** - Restart failed or stuck jobs
- **Skip** - Mark file as complete without processing
- **Delete** - Remove file from queue
- **Re-encode** - Re-process completed files
- **Scan Library** - Trigger new media scan

## ⚙️ Configuration

### Quality Optimization

The system uses lookup tables to determine optimal encoding settings:

**quality_lookup.json** - Video CRF values
```json
{
  "SD": {"x264": 28, "x265": 30, "av1": 35},
  "720p": {"x264": 26, "x265": 28, "av1": 33},
  "1080p": {"x264": 24, "x265": 26, "av1": 31},
  "1440p": {"x264": 22, "x265": 24, "av1": 29},
  "4K": {"x264": 20, "x265": 22, "av1": 27}
}
```

**audio_codec_lookup.json** - Opus bitrates
```json
{
  "1": 64,
  "2": 96,
  "6": 256,
  "8": 320
}
```

**Editing Configuration:**

Docker:
```bash
# Edit files in persistent volume
nano master-data/config/quality_lookup.json
nano master-data/config/audio_codec_lookup.json

# Restart to apply
docker compose restart
```

Native:
```bash
# Edit files directly
nano quality_lookup.json
nano audio_codec_lookup.json
```

Workers automatically fetch updated config from master on startup.

### Docker Compose Files

**docker-compose.master.yml** - Master server only
```yaml
services:
  master:
    build: .
    ports:
      - "8090:8090"
    volumes:
      - ./master-data:/data
      - ./Movies:/media/Movies
      - ./TV:/media/TV
    environment:
      - MEDIA_DIRS=/media/Movies,/media/TV
      - SVT_AV1_PRESET=8
```

**docker-compose.worker.yml** - Worker with shared storage
```yaml
services:
  worker:
    build: .
    volumes:
      - ./worker-data:/data
      - /tmp/worker_temp:/tmp/av1_transcoding
    environment:
      - MASTER_URL=http://192.168.1.100:8090
      - FILE_DISTRIBUTION_MODE=false
      - SMB_HOST=192.168.1.10
      - SMB_SHARE=Media
```

**docker-compose.filedist-test.yml** - File distribution test
```yaml
services:
  master:
    # Master has access to media
  worker1:
    # Worker has NO media access
    environment:
      - FILE_DISTRIBUTION_MODE=true
```

## 📊 Performance

### Scaling Examples

Processing 100 files (30 minutes each at SVT-AV1 preset 8):

| Workers | Time | Speedup |
|---------|------|---------|
| 1 | 50 hours | 1× |
| 2 | 25 hours | 2× |
| 4 | 12.5 hours | 4× |
| 8 | 6.25 hours | 8× |

### Encoding Presets

SVT-AV1 preset performance (varies by hardware):

| Preset | Quality | Speed | Use Case |
|--------|---------|-------|----------|
| 0-3 | Excellent | Very Slow | Archival, maximum quality |
| 4-6 | Very Good | Slow | High-quality encodes |
| 7-9 | Good | Medium | Balanced (recommended) |
| 10-13 | Fair | Fast | Quick previews, testing |

**Recommended:** Preset 8 for balanced quality and speed.

### Space Savings

Typical compression results (varies by source):

| Source | Target | Savings |
|--------|--------|---------|
| H.264 High Bitrate | AV1 | 40-60% |
| H.265/HEVC | AV1 | 20-40% |
| VP9 | AV1 | 10-25% |
| Old Codecs (MPEG-2) | AV1 | 60-80% |

## 🔧 Troubleshooting

### Common Issues

**Workers Not Connecting:**
```bash
# Test master accessibility
curl http://MASTER_IP:8090/api/status

# Check firewall
sudo ufw allow 8090/tcp

# View master logs
docker compose logs -f master
```

**Jobs Not Processing:**
```bash
# Check worker status in web UI
# Verify files are in "pending" status
# Check worker logs
docker compose logs -f worker

# Verify media directory access
docker compose exec worker ls -la /media
```

**Web UI Not Updating:**
```bash
# Check WebSocket connection in browser console
# Clear browser cache
# Verify no proxy blocking WebSocket
```

**Low Processing Speed:**
```bash
# Check CPU usage
docker stats

# Adjust preset (higher = faster)
docker compose down
# Edit SVT_AV1_PRESET in compose file
docker compose up -d

# Verify nice/ionice settings
docker compose exec worker ps aux | grep ffmpeg
```

### Logs

**Docker:**
```bash
# Master logs
docker compose -f docker-compose.master.yml logs -f

# Worker logs
docker compose -f docker-compose.worker.yml logs -f

# Specific container
docker logs av1-master --tail 100 -f
```

**Native:**
```bash
# Check system logs
journalctl -u av1-transcode -f

# Application logs (if configured)
tail -f /var/log/av1-transcode.log
```

## 📁 Project Structure

```
av1/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Multi-stage Docker build
├── docker-entrypoint.sh         # Container startup script
│
├── docker-compose.master.yml    # Master server
├── docker-compose.worker.yml    # Worker node
├── docker-compose.filedist-test.yml  # File distribution test
│
├── transcode.py                 # Standalone server
├── master_server.py             # Master coordinator
├── worker_client.py             # Worker client
├── init_config.py               # Config initialization
│
├── config.json                  # Native Python config
├── quality_lookup.json          # Video CRF defaults
├── audio_codec_lookup.json      # Audio bitrate defaults
│
├── lib/
│   ├── config.py               # Configuration management
│   ├── database.py             # SQLite queue + stats
│   ├── scanner.py              # Media directory scanner
│   ├── probe.py                # FFmpeg metadata extraction
│   ├── quality.py              # Quality lookup logic
│   ├── transcoder.py           # Encoding engine
│   ├── master_coordinator.py   # Worker coordination
│   └── web_api.py              # Flask API routes
│
└── web/
    ├── master-new.html         # Modern web interface (default)
    ├── master-new.js           # Modern UI JavaScript
    ├── style-new.css           # Modern UI styles
    ├── master.html             # Legacy interface
    ├── master.js               # Legacy JavaScript
    └── style.css               # Legacy styles
```

## 🔐 Security Considerations

### Production Deployment

**Network Security:**
- Use HTTPS reverse proxy (nginx, Caddy)
- Implement authentication (Basic Auth, OAuth)
- Restrict master port access via firewall
- Use VPN for remote workers

**File Security:**
- Run containers as non-root user
- Use read-only media mounts where possible
- Implement backup strategy
- Enable testing mode initially

**SMB/NFS:**
- Use credentials with minimum required permissions
- Store passwords in .env file (not in compose yaml)
- Use SMB3 or NFS4 with encryption

### Example Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name transcode.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://localhost:8090;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 🛠️ Development

### Building

```bash
# Build Docker image
docker build -t av1-transcoder .

# Build specific architecture
docker buildx build --platform linux/amd64,linux/arm64 -t av1-transcoder .
```

### Testing

```bash
# Run master + 2 workers locally
docker compose -f docker-compose.filedist-test.yml up

# View logs
docker compose -f docker-compose.filedist-test.yml logs -f

# Stop and cleanup
docker compose -f docker-compose.filedist-test.yml down
```

### Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -am 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

## 📝 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- **SVT-AV1** - Scalable Video Technology for AV1
- **Opus** - High-quality audio codec
- **FFmpeg** - Multimedia processing framework
- **Flask** - Python web framework
- **Socket.IO** - Real-time bidirectional communication

## 📚 Additional Resources

- [AV1 Encoding Guide](https://trac.ffmpeg.org/wiki/Encode/AV1)
- [SVT-AV1 Documentation](https://gitlab.com/AOMediaCodec/SVT-AV1)
- [Opus Codec](https://opus-codec.org/)
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)

---

**Version:** 2.0.0  
**Last Updated:** October 2025
