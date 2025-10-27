# AV1 Transcoding System - Distributed Mode

## Overview

Your AV1 transcoding system now supports distributed processing across multiple computers. The system uses a master/worker architecture where:

- **Master Server** coordinates all work and provides a unified web interface
- **Worker Clients** on different computers process the actual transcoding jobs

## Quick Start

### 1. Start Master Server (Main Computer)

```bash
cd /home/wieczorek/av1
./start_master.sh
```

The master server will:
- Start on port 8090
- Scan media directories for files to transcode
- Wait for workers to connect
- Provide web interface at http://localhost:8090

### 2. Start Worker Clients (Additional Computers)

On each additional computer that should help with transcoding:

```bash
cd /path/to/av1
./start_worker.sh http://MASTER_IP:8090
```

Replace `MASTER_IP` with the IP address of your master server (e.g., `192.168.1.100`)

Each worker will:
- Register with the master server
- Request jobs when idle
- Report progress in real-time
- Process files using the same quality settings

### 3. Monitor Progress

Open http://MASTER_IP:8090 in your browser to see:
- All connected workers and their status
- Current jobs being processed on each worker
- Overall progress across all workers
- System statistics (CPU, memory, jobs completed)
- Real-time progress updates

## Architecture

```
┌─────────────────────────────────────────┐
│         Master Server (Port 8090)       │
│  - Job coordination                     │
│  - Worker management                    │
│  - Web UI                               │
│  - Progress aggregation                 │
└─────────────┬───────────────────────────┘
              │
    ┌─────────┴──────────┬──────────────┐
    │                    │              │
┌───▼────┐          ┌───▼────┐     ┌───▼────┐
│Worker 1│          │Worker 2│     │Worker 3│
│        │          │        │     │        │
│Transcode│         │Transcode│    │Transcode│
│ Jobs   │          │ Jobs   │     │ Jobs   │
└────────┘          └────────┘     └────────┘
```

## Features

### Master Server
- REST API for worker communication
- WebSocket real-time updates
- Worker health monitoring (30s timeout)
- Automatic job reassignment on worker failure
- Statistics tracking per worker
- Unified web interface

### Worker Client
- Automatic registration with master
- Heartbeat monitoring (every 10s)
- Progress reporting during transcoding
- CPU/memory usage reporting
- Graceful shutdown handling
- Local temp file processing

### Web Interface
- Real-time worker status cards
- Job queue visibility
- Per-worker progress tracking
- Overall statistics dashboard
- CPU/memory monitoring
- Auto-refresh and WebSocket updates

## Requirements

### Network
- All workers must have network access to master server on port 8090
- Workers must have read/write access to media files (shared NAS)
- Firewall must allow HTTP and WebSocket connections

### Storage
- Media files should be on shared network storage (NAS)
- All machines should mount media directories at same paths
- OR configure different paths in each worker's config.json

### Software
- Python 3.12+
- FFmpeg with libsvtav1 and libopus
- Flask, Flask-SocketIO, Flask-CORS
- psutil, requests

## Configuration

### Master (config.json)
```json
{
  "media_directories": [
    "/mnt/nas/Movies",
    "/mnt/nas/TV"
  ],
  "temp_directory": "/tmp/av1_transcoding",
  "web_port": 8090,
  "testing_mode": false
}
```

### Workers
- Copy entire project to each worker machine
- Ensure same media directories are accessible
- Install dependencies: `pip install -r requirements.txt`
- Start with: `./start_worker.sh http://MASTER_IP:8090`

## Monitoring

### Worker Status Indicators
- 🟢 **Idle**: Ready for jobs
- 🟡 **Processing**: Actively transcoding
- ⚫ **Offline**: Disconnected or timed out

### Job Status
- **Pending**: Waiting to be assigned
- **Processing**: Currently transcoding
- **Completed**: Successfully transcoded
- **Failed**: Transcoding failed or not worthwhile (< 5% savings)

## Troubleshooting

### Worker won't connect
```bash
# Check master is running
curl http://MASTER_IP:8090/api/status

# Check network connectivity
ping MASTER_IP

# Check firewall
sudo ufw status
```

### Jobs not being processed
1. Verify workers show as "idle" in web UI
2. Check media directories are accessible from workers
3. Review master server logs
4. Verify files are in "pending" status

### Progress not updating
- Check browser console for WebSocket errors
- Verify no proxy/firewall blocking WebSocket
- Try refreshing the page (auto-refresh every 5s)

## Files Added

New files for distributed system:
- `master_server.py` - Master coordination server
- `worker_client.py` - Worker processing client
- `lib/master_coordinator.py` - Worker/job management logic
- `web/master.html` - Master web interface
- `web/master.js` - Master UI JavaScript
- `start_master.sh` - Master startup script
- `start_worker.sh` - Worker startup script
- `DISTRIBUTED.md` - Detailed documentation

Existing files (still work standalone):
- `transcode.py` - Original standalone server
- `web/index.html` - Original web UI

## Upgrading from Standalone

Your original standalone system (`transcode.py`) still works. The distributed system is completely separate.

To switch to distributed mode:
1. Stop standalone server if running
2. Start master server: `./start_master.sh`
3. Start workers on other machines
4. Access new UI at http://localhost:8090

The same database and configuration files are used, so your queue and statistics are preserved.

## Performance

With distributed processing:
- **1 worker**: ~1 file at a time (same as standalone)
- **3 workers**: ~3 files in parallel
- **5 workers**: ~5 files in parallel

Processing speed scales linearly with worker count, limited only by:
- Network bandwidth (for reading/writing files)
- NAS I/O performance
- Available worker resources

## Safety

- Original files preserved in testing mode
- Workers fail gracefully on disconnect
- Master reassigns jobs from offline workers
- Minimum 5% savings required before replacing original
- All operations logged for troubleshooting
