# AV1 Distributed Transcoding System# 🎬 AV1 Distributed Transcoding System



A distributed video transcoding system that converts video files to AV1 format using SVT-AV1 encoder across multiple worker machines.High-performance distributed media transcoding system that converts your entire library to AV1 (SVT-AV1) with Opus audio. Features modern web interface, smart quality optimization, and distributed processing across multiple machines.



## Features## ✨ Features



- **Distributed Processing**: Master/worker architecture for parallel transcoding### Core Capabilities

- **File Distribution Mode**: Workers download files via HTTP (no shared storage needed)- ✅ **AV1 Encoding** - SVT-AV1 with configurable presets (0-13)

- **HDR Support**: Automatically detects and preserves HDR10 metadata, skips dynamic HDR (HDR10+, Dolby Vision)- ✅ **Opus Audio** - High-quality audio with excellent compression

- **Quality-Based Encoding**: Automatic CRF selection based on resolution- ✅ **Smart Quality** - Automatic CRF/bitrate based on source resolution and codec

- **Web Interface**: Real-time monitoring with progress tracking- ✅ **Modern Web UI** - Real-time monitoring with detailed progress tracking

- **Docker-Based**: Easy deployment with Docker Compose- ✅ **Safe Processing** - Testing mode, backups, atomic file operations

- **GitHub Actions CI/CD**: Automated builds to GitHub Container Registry- ✅ **Efficient** - Only replaces files with 5%+ space savings



## Quick Start### Distributed Processing

- ✅ **Master/Worker Architecture** - Coordinate jobs across multiple computers

### 1. Master Server + Local Worker (Linux)- ✅ **Auto Job Distribution** - Workers request jobs when idle

- ✅ **Real-time Monitoring** - Single unified web interface

```bash- ✅ **Health Monitoring** - Auto-detect and recover from worker failures

# Clone the repository- ✅ **Linear Scaling** - Add workers for proportional speedup

git clone https://github.com/Hack2C/av1-distributed-encoder.git- ✅ **File Distribution Mode** - HTTP-based transfers (no shared storage needed)

cd av1-distributed-encoder

### Advanced Features

# Start master + 1 local worker- ✅ **Job Controls** - Cancel, retry, skip, delete operations

docker compose -f docker-compose.test.yml up -d- ✅ **Detailed Tracking** - Resolution, codec, bitrate, worker assignment

- ✅ **Time Estimates** - Per-file and overall ETA with processing speed

# Access web interface- ✅ **Process Priority** - Configurable nice/ionice for background operation

http://localhost:8090- ✅ **HDR Support** - Automatic detection and preservation

```- ✅ **Multi-track** - Preserves all audio tracks, subtitles, and metadata



### 2. Windows Worker## 🚀 Quick Start



Edit `docker-compose.windows-worker.yml` and replace `MASTER_IP_HERE` with your master server IP:### Docker (Recommended)



```yaml**Master Server:**

command: python3 worker_client.py http://192.168.1.100:8090```bash

```# Create config directory

mkdir -p master-data/config

Then start the worker:

# Start master

```bashdocker compose -f docker-compose.master.yml up -d

docker compose -f docker-compose.windows-worker.yml up -d

```# Access web UI

open http://localhost:8090

## Architecture```



- **Master Server**: Coordinates jobs, serves web UI, provides file downloads**Worker Node:**

- **Workers**: Process transcoding jobs, download files from master, upload results```bash

- **File Distribution**: HTTP-based file transfer (no NFS/SMB required)# Copy worker config

cp docker-compose.worker.yml docker-compose.worker-1.yml

## Configuration

# Edit configuration (set MASTER_URL and media paths)

### Quality Lookup (`quality_lookup.json`)nano docker-compose.worker-1.yml



Defines CRF values based on resolution:# Start worker

- 4K (2160p): CRF 24docker compose -f docker-compose.worker-1.yml up -d

- 1440p: CRF 25```

- 1080p: CRF 26

- 720p: CRF 27### Native Python

- 480p: CRF 28

**Standalone Mode:**

### Audio Codec (`audio_codec_lookup.json`)```bash

# Install dependencies

Defines Opus bitrates for different source audio formats.pip3 install -r requirements.txt



### Environment Variables# Edit config.json

nano config.json

#### Master

- `MEDIA_DIRS`: Comma-separated list of media directories# Run

- `TESTING_MODE`: Creates `.bak` backups instead of deleting originalspython3 transcode.py

- `SVT_AV1_PRESET`: Encoder preset (0=slowest/best, 13=fastest/worst)```

- `PUID/PGID`: User/Group ID for file ownership (default: 1000)

**Distributed Mode:**

#### Worker```bash

- `FILE_DISTRIBUTION_MODE=true`: Enable file download mode# Master

- `MEDIA_DIRS`: Leave empty for file distribution mode./start_master.sh

- `SVT_AV1_PRESET`: Encoder preset

- `PUID/PGID`: User/Group ID for file ownership (default: 1000)# Worker

./start_worker.sh http://MASTER_IP:8090

## HDR Handling```



The system automatically:## 📦 Installation

- **Preserves HDR10** (static metadata): Transcoded with proper color transfer and primaries

- **Skips HDR10+**: Dynamic metadata cannot be preserved, file is skipped### Prerequisites

- **Skips Dolby Vision**: Dynamic metadata cannot be preserved, file is skipped

**Docker Method:**

## Docker Compose Files- Docker Desktop (Windows/Mac) or Docker Engine (Linux)

- Access to media files (local or network share)

- `docker-compose.test.yml`: Master + 1 local worker for testing

- `docker-compose.master.yml`: Master server only**Native Method:**

- `docker-compose.worker.yml`: Local worker only  - Python 3.12+

- `docker-compose.windows-worker.yml`: Windows worker using GHCR image- FFmpeg with libsvtav1 and libopus support



## Monitoring### Configuration



Web interface (http://localhost:8090) provides:**Environment Variables:**

- Overall statistics (files processed, savings)```bash

- Worker status and performance# Application

- File queue with progress trackingMEDIA_DIRS=/media/Movies,/media/TV        # Media directories (comma-separated)

- Real-time updates via WebSocketsTEMP_DIR=/tmp/av1_transcoding             # Temporary processing directory

WEB_PORT=8090                              # Web interface port

## File OwnershipTESTING_MODE=true                          # Keep backup files for verification



Files are created with the user/group specified by `PUID` and `PGID` (default: 1000:1000).# Master Connection (Workers Only)

MASTER_URL=http://192.168.1.100:8090      # Master server URL

## Temp Directory Cleanup

# Encoding Settings

Workers automatically:SVT_AV1_PRESET=8                          # 0-13 (0=slowest/best, 8=balanced, 13=fastest)

- Clean temp directory on startup

- Clean temp files after each job (success or failure)# Process Priority

- Remove abandoned files from crashes/restartsNICE_LEVEL=19                              # CPU priority (0-19, 19=lowest)

IONICE_CLASS=3                             # I/O priority (1-3, 3=idle)

## Repository

# File Distribution (Optional)

https://github.com/Hack2C/av1-distributed-encoderFILE_DISTRIBUTION_MODE=false               # true=HTTP transfer, false=shared storage


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
