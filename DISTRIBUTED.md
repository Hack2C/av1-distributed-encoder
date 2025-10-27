# Distributed AV1 Transcoding System

This system supports distributed transcoding across multiple machines with a master/worker architecture.

## Architecture

- **Master Server**: Coordinates jobs, manages workers, provides web UI
- **Worker Clients**: Process transcoding jobs, report progress to master

## Setup

### Master Server

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure settings in `config.json`

3. Start the master server:
```bash
python3 master_server.py
```

The master server will:
- Listen on port 8090 (configurable)
- Scan media directories for files to transcode
- Accept worker registrations
- Distribute jobs to available workers
- Provide web interface at http://localhost:8090

### Worker Client

Workers can run on any machine with network access to the master server.

1. Copy the project to the worker machine

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure FFmpeg is installed with libsvtav1 and libopus support

4. Start the worker:
```bash
python3 worker_client.py http://MASTER_IP:8090
```

Replace `MASTER_IP` with the IP address of your master server.

The worker will:
- Register with the master server
- Request jobs when idle
- Process transcoding jobs
- Report progress in real-time
- Send heartbeats to indicate availability

## Web Interface

Access the master web interface at:
```
http://MASTER_IP:8090
```

The interface shows:
- Active workers and their status
- Current jobs being processed
- Overall progress and statistics
- Per-worker CPU/memory usage
- Real-time progress updates

## Configuration

### Master Server

Edit `config.json`:
```json
{
  "media_directories": [
    "/path/to/Movies",
    "/path/to/TV"
  ],
  "temp_directory": "/tmp/av1_transcoding",
  "web_port": 8090,
  "testing_mode": false
}
```

### Worker Settings

Workers inherit configuration from `config.json` on the worker machine for:
- Temp directory location
- Testing mode (keeps original files as .bak)

## Network Requirements

- Workers need HTTP/WebSocket access to master server
- Workers need read/write access to media files (shared network storage)
- Default port: 8090 (configurable)

## Monitoring

### Worker Status

- **Idle**: Worker is connected and waiting for jobs
- **Processing**: Worker is actively transcoding
- **Offline**: Worker has disconnected or timed out (30s)

### Job Status

- **Pending**: Waiting to be assigned
- **Processing**: Currently being transcoded
- **Completed**: Successfully transcoded
- **Failed**: Transcoding failed or not worthwhile

## Troubleshooting

### Worker won't connect
- Check firewall settings on master server
- Verify master server is running and accessible
- Check network connectivity between worker and master

### Jobs not being assigned
- Verify workers are in "idle" status
- Check that files exist in media directories
- Review master server logs for errors

### Progress not updating
- WebSocket connection may be blocked by firewall
- Check browser console for connection errors
- Verify both HTTP and WebSocket ports are accessible

## Performance Tips

1. **Network Storage**: Ensure fast network access to media files
2. **Worker Resources**: Assign workers based on available CPU/memory
3. **Temp Directory**: Use fast local storage for temp files
4. **Multiple Workers**: Add more workers to process files in parallel

## Safety Features

- Workers send heartbeats every 10 seconds
- Master detects offline workers after 30 seconds of no contact
- Jobs from offline workers are automatically marked as failed
- Original files preserved in testing mode
- Minimum 5% savings required before replacing original
